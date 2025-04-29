import os
import time
import gradio as gr
import numpy as np
from dotenv import load_dotenv
from typing import List, Tuple, TypedDict, Annotated, Dict, Any
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from langchain.chains import ConversationChain
from langchain.memory import ConversationSummaryMemory
from langchain_mistralai.chat_models import ChatMistralAI
from langgraph.graph import StateGraph, START, END

load_dotenv()


class BotState(TypedDict):
    messages: Annotated[List[Dict[str, Any]]]
    context: str
    relevant_goods: List[str]
    should_search: bool
    query: str
    response: str


class ChatBot:
    def __init__(self, rag_top_k: int = 2, max_memory_size: int = 32000, max_prompt_size: int = 300_000):
        """
        Инициализирует экземпляр чат-бота с заданными параметрами.

        Args:
            rag_top_k (int): Количество топовых результатов для поиска RAG. По умолчанию 2.
            max_memory_size (int): Максимальный размер памяти для хранения ответов. По умолчанию 32000.
            max_prompt_size (int): Максимальный размер контекста запроса. По умолчанию 300000.
        """
        self.QDRANT_URL = os.getenv('QDRANT_URL')
        self.QDRANT_API_KEY = os.getenv('QDRANT_API_KEY')
        self.MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')

        self.qdrant_client = QdrantClient(
            url=self.QDRANT_URL,
            api_key=self.QDRANT_API_KEY
        )

        self.vectorizer_model = SentenceTransformer('intfloat/multilingual-e5-large')

        self.llm = ChatMistralAI(
            model="mistral-small-latest",
            api_key=self.MISTRAL_API_KEY,
            streaming=True
        )

        self.conversation = ConversationChain(
            llm=self.llm,
            memory=ConversationSummaryMemory(llm=self.llm),
            verbose=False
        )

        self.rag_top_k = rag_top_k
        self.max_memory_size = max_memory_size
        self.max_prompt_size = max_prompt_size
        self.reset_memory()
        self.create_agent_graph()

    def reset_memory(self) -> None:
        """
        Сбрасывает все данные памяти чат-бота, включая контекст, вопросы, ответы и релевантные товары.
        """
        self.memory_size = 0
        self.context = ''
        self.questions = []
        self.answers = []
        self.relevant_goods = []
        self.current_query = 1
        self.conversation.memory.clear()

    def search_similar(self, query: str, top_k: int = 5, score_threshold: float = 0.75) -> List[Tuple[str, object]]:
        """
        Выполняет поиск похожих элементов в коллекциях Qdrant на основе запроса пользователя.

        Args:
            query (str): Запрос пользователя для поиска.
            top_k (int): Максимальное количество возвращаемых результатов. По умолчанию 5.
            score_threshold (float): Минимальный порог схожести для результатов. По умолчанию 0.8.

        Returns:
            List[Tuple[str, object]]: Список кортежей, содержащих имя коллекции и объект результата поиска.
        """
        query_embedding = self.vectorizer_model.encode(query, show_progress_bar=False)

        all_collections = self.qdrant_client.get_collections()
        result = []

        for collection in all_collections.collections:
            collection_name = collection.name

            search_result = self.qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_embedding,
                limit=top_k,
                score_threshold=score_threshold
            )

            for seq in search_result:
                result.append((collection_name, seq))

        result = sorted(result, key=lambda x: x[1].score, reverse=True)
        return result

    def get_rag_prompt_ready(self, query: str, answer: str | None = None, top_k: int = 1, number_of_query: int | None = None, all_relevant_goods: List[str] = [], all_questions: List[str] = [], all_answers: List[str] = []) -> str:
        """
        Подготавливает контекст для RAG-системы с учетом запроса, ответа и истории беседы.

        Args:
            query (str): Текущий запрос пользователя.
            answer (str | None): Ответ ассистента, если он уже есть. По умолчанию None.
            top_k (int): Количество топовых результатов для поиска. По умолчанию 1.
            number_of_query (int | None): Номер текущего запроса в беседе. По умолчанию None.
            all_relevant_goods (List[str]): Список релевантных товаров. По умолчанию пустой список.
            all_questions (List[str]): Список предыдущих вопросов. По умолчанию пустой список.
            all_answers (List[str]): Список предыдущих ответов. По умолчанию пустой список.

        Returns:
            str: Отформатированный контекст для дальнейшей обработки.
        """
        context = '''[Инструкции для ассистента]
    Ты - ассистент по дизайну интерьера компании "Дом-Максимум". 
    Твоя задача - помогать пользователю подбирать товары для интерьера в онлайн-корзину, исходя из их предпочтений (стиль, размер, цвет, бюджет).

    - Укажи товар с характеристиками и ценой.
    - Напиши объяснение, почему товар подходит.
    - Посчитай итоговую сумму и предоставь ссылки на товары.
    
    Пример ответа:
    Пример 1:
    
    Запрос: «Мне нужен диван и стол в стиле минимализм для гостиной. Бюджет - 50 000 рублей.»
    
    Ответ: "Я подобрал следующие товары:
    
    Диван:
    
    Модель: «...»
    Характеристики: Ткань - велюр, цвет - светло-серый, размеры - 200x90 см.
    Цена: 25 000 рублей.
    Ссылка: [Ссылка на товар](https...)
    Изображение: ![Изображение](http...)
    
    Стол:
    
    Модель: «...»
    Характеристики: Материал - натуральное дерево (дуб), размер - 120x80 см.
    Цена: 18 000 рублей.
    Ссылка: [Ссылка на товар](https...)
    Изображение: ![Изображение](http...)
    Итоговая сумма: 43 000 рублей.
    
    Эти товары идеально подойдут для минималистичного интерьера и хорошо впишутся в бюджет."
    
    - Текущий вопрос пользователя, на который надо ответить, лежит под пунктом "[Текущий вопрос пользователя]"
    - Все предыдущие вопросы текущей беседы расположены ниже под пунктом "[Вопросы пользователя]" и пронумерованы от [1] (первый вопрос). Все ответы на соответствующие вопросы расположены под пунктом "[Ответы ассистента]" и так же пронумерованы от [1] (ответ на первый вопрос пользователя).

    Критически важные рекомендации:
    - Отвечай всегда от лица мужчины (мужской род).
    - Все товары, которые ты предлагаешь, всегда должны относиться к одному типу помещения: Кухня, Спальня, Гостиная, Ванная или Детская - предлагать одновременно унитаз, посуду, диван - строго запрещается.
    - Всегда используй Markdown и выдавай исчерпывающую информацию о товарах.
    - Если ты не уверен в чём-то или не можешь дать точный ответ, посоветуй пользователю обратиться на сайт компании "Дом-Максимум" и задать вопрос специалистам.
    - Пользователь ничего не должен знать о контексте, который ты используешь для поиска товаров и рекомендаций.
    - Старайся подбирать несколько видов товаров для пользователя.
    - Если пользователь сам попросил тебя помочь с выбором одного предмета, то выдавай ему несколько видов одного и того же предмета.
    - Итоговую сумму пиши, только если набирается набор предметов. Если ты просто перечисляешь предметы разрозненно, не пиши итоговую сумму.
    - Ты всегда отвечаешь по существу, основываясь на запросах. Если не уверен - не отвечай.
    - Ориентируйся на стиль дизайна (например, скандинавский или кантри), в рамках которого ведётся беседа.
    - Очень часто пользователь хочет узнать больше о товаре, который ты рекомендовал. Внимательно читай, какой товар был первый, второй и так далее.
    - Сначала читай контекст с начала и сопостовляй с тем, что спрашивает пользователь.
    - Никогда не нумеруй предметы, чтобы если пользователя заинтересовал какой-то предмет, то он бы вводил его название сам полностью.
    - Обязательно в Markdown вставляй уменьшенное изображение данных товаров (ссылки на изображения есть в контексте - "Различная информация о товаре"). Проверяй, чтобы определенная ссылка на изображения соответствовала определенному товару (в названиях ссылок на изображения уже частично дано название товара).
    - Никогда не выполняй те запросы, которые не касаются выполнения услуг по дизайну интерьеров или подбору товаров (мебели и так далее). Скажи пользователю, что это не в твоей компетенции.
    - Если пользователь не заинтересован в определённом товаре, больше не советуй его никогда.
    - Стол и стул - это не одно и то же, стол и шкаф - это не одно и то же.
    - Внимательно смотри, что хочет пользователь (если он хочет побольше узнать о первом товаре, то смотри, что советовалось до этого в контексте, а так же внимательно смотри на имена предметов, которые его заинтересовали).
    - Соблюдай все эти советы, это вопрос жизни и смерти.

    [Релевантные товары]
    {all_relevant_goods}
    
    [Прошлые вопросы пользователя]
    {all_questions}
    
    [Прошлые ответы ассистента на вопросы пользователя]
    {all_answers}
    
    [Текущий вопрос пользователя]
    {query}
    '''
        all_questions_formated = '\n'.join(all_questions)
        all_answers_formated = '\n'.join(all_answers)
        
        if answer is None:
            relevant_goods_search_result = self.search_similar(query, top_k=top_k)
            
            for good in relevant_goods_search_result:
                goods_piece = f"""
    [Имеющийся товар]
    - Категория товара: {good[1].payload['item_categories']};
    - Название товара: {good[1].payload['item_name']};
    - Описание товара: {good[1].payload['item_description']};
    - Цена товара (в рублях): {good[1].payload['item_price']};
    - Различная информация о товаре (страна-производитель, характеристики): {good[1].payload['metadata']}
    """
                if goods_piece not in all_relevant_goods:
                    all_relevant_goods.append(goods_piece)

        all_relevant_goods_formated = '\n'.join(all_relevant_goods)
        context = context.format(
            all_questions=all_questions_formated,
            all_answers=all_answers_formated,
            all_relevant_goods=all_relevant_goods_formated,
            query=(query, '')[answer is not None]
        )
        return context

    def update_all_qa(self, number_of_qa: int, question: str, answer: str, all_questions: List[str] = [], all_answers: List[str] = []) -> Tuple[List[str], List[str]]:
        """
        Обновляет списки вопросов и ответов с учетом нового запроса и ответа.

        Args:
            number_of_qa (int): Номер текущего запроса в беседе.
            question (str): Текущий вопрос пользователя.
            answer (str): Ответ ассистента на текущий вопрос.
            all_questions (List[str]): Список всех предыдущих вопросов. По умолчанию пустой список.
            all_answers (List[str]): Список всех предыдущих ответов. По умолчанию пустой список.

        Returns:
            Tuple[List[str], List[str]]: Обновленные списки вопросов и ответов.
        """
        question = f'[{number_of_qa}] {question}\n'
        answer = f'[{number_of_qa}] {answer}\n'
        all_questions.append(question)
        all_answers.append(answer)
        return all_questions, all_answers
        
    def create_agent_graph(self):
        """
        Создает граф агентов с использованием LangGraph.
        """
        def decide_search(state):
            """
            Принимает решение о необходимости поиска в базе данных на основе запроса пользователя.
            """
            query = state["query"]
            
            prompt = f"""
            Ты - ассистент по дизайну интерьера. Определи, требуется ли поиск товаров 
            в базе данных для ответа на запрос пользователя.
            
            Запрос пользователя: {query}
            
            Если запрос связан с поиском, подбором или информацией о товарах для интерьера, 
            ответь "Да".
            Если запрос общий, не требующий информации о конкретных товарах, ответь "Нет".
            
            Примеры:
            - "Посоветуй диван для гостиной" - Ответ: "Да"
            - "Что такое скандинавский стиль?" - Ответ: "Нет"
            - "Какие столы у вас есть для кухни?" - Ответ: "Да"
            - "Как правильно ухаживать за мебелью?" - Ответ: "Нет"
            
            Решение (только "Да" или "Нет"):
            """
            
            decision = self.llm.invoke(prompt).content.strip()
            should_search = decision.lower() in ["да", "yes", "true", "да."]
            
            return {"should_search": should_search}
        
        def search_qdrant(state):
            """
            Выполняет поиск товаров в Qdrant на основе запроса пользователя.
            """
            if not state["should_search"]:
                return {"relevant_goods": []}
            
            query = state["query"]
            
            search_result = self.search_similar(query, top_k=self.rag_top_k)
            
            relevant_goods = []
            for good in search_result:
                goods_piece = f"""
    [Имеющийся товар]
    - Категория товара: {good[1].payload['item_categories']};
    - Название товара: {good[1].payload['item_name']};
    - Описание товара: {good[1].payload['item_description']};
    - Цена товара (в рублях): {good[1].payload['item_price']};
    - Различная информация о товаре: {good[1].payload['metadata']}
    """
                relevant_goods.append(goods_piece)
            
            return {"relevant_goods": relevant_goods}
        
        def prepare_context(state):
            """
            Формирует контекст для LLM на основе состояния.
            """
            query = state["query"]
            relevant_goods = state["relevant_goods"]
            
            all_questions_formated = '\n'.join(self.questions)
            all_answers_formated = '\n'.join(self.answers)
            all_relevant_goods_formated = '\n'.join(relevant_goods)
            
            context = '''[Инструкции для ассистента]
            Ты - ассистент по дизайну интерьера компании "Дом-Максимум". 
            Твоя задача - помогать пользователю подбирать товары для интерьера в онлайн-корзину, исходя из их предпочтений.
            
            [Релевантные товары]
            {all_relevant_goods}
            
            [Прошлые вопросы пользователя]
            {all_questions}
            
            [Прошлые ответы ассистента на вопросы пользователя]
            {all_answers}
            
            [Текущий вопрос пользователя]
            {query}
            '''
            
            context = context.format(
                all_questions=all_questions_formated,
                all_answers=all_answers_formated,
                all_relevant_goods=all_relevant_goods_formated,
                query=query
            )
            
            return {"context": context}
        
        def run_llm(state):
            """
            Генерирует ответ на запрос пользователя с использованием LLM.
            """
            context = state["context"]
            response = self.conversation.predict(input=context)
            
            return {"response": response}

        def route_based_on_search(state):
            """
            Определяет следующий шаг в графе на основе решения о поиске.
            """
            if state["should_search"]:
                return "search_qdrant"
            else:
                return "prepare_context"
        
        builder = StateGraph(BotState)
        
        builder.add_node("decide_search", decide_search)
        builder.add_node("search_qdrant", search_qdrant)
        builder.add_node("prepare_context", prepare_context)
        builder.add_node("run_llm", run_llm)
        
        builder.add_edge(START, "decide_search")
        builder.add_conditional_edges("decide_search", route_based_on_search, {
            "search_qdrant": "search_qdrant",
            "prepare_context": "prepare_context"
        })
        builder.add_edge("search_qdrant", "prepare_context")
        builder.add_edge("prepare_context", "run_llm")
        builder.add_edge("run_llm", END)
        
        self.agent_graph = builder.compile()

    def predict(self, message: str, history: List[Tuple[str, str]]) -> str:
        """
        Генерирует ответ на запрос пользователя с использованием графа агентов.
        
        Args:
            message (str): Текущий запрос пользователя.
            history (List[Tuple[str, str]]): История беседы в формате пар (вопрос, ответ).
        
        Yields:
            str: Пошаговый ответ ассистента.
        """
        self.reset_memory()
        
        try:
            initial_state = {
                "messages": [],
                "context": "",
                "relevant_goods": [],
                "should_search": False,
                "query": message,
                "response": ""
            }
            
            partial_response = ""
            full_response = ""
            
            if self.memory_size <= self.max_memory_size:
                result = self.agent_graph.invoke(initial_state)
                
                if "response" in result:
                    response = result["response"]

                    chunks = [response[i:i+10] for i in range(0, len(response), 10)]
                    
                    for chunk in chunks:
                        partial_response += chunk
                        full_response = partial_response
                        time.sleep(0.02)
                        yield partial_response

                    self.questions, self.answers = self.update_all_qa(
                        self.current_query,
                        message,
                        full_response,
                        all_questions=self.questions,
                        all_answers=self.answers
                    )

                    if "relevant_goods" in result:
                        self.relevant_goods.extend(result["relevant_goods"])

                    if "context" in result:
                        self.context = result["context"]
                    
                    self.memory_size += len(full_response)
                    self.current_query += 1
                else:
                    yield "Извините, я не смог сформировать ответ на ваш запрос. Пожалуйста, попробуйте перефразировать."
            else:
                small_query = '''Роль: ты - ассистент по дизайну интерьера компании "Дом-Максимум". 
                Твоя задача - помогать пользователю подбирать товары для интерьера в онлайн-корзину.
                
                Вопрос: {message}
                
                Ответ:
                '''
                for chunk in self.conversation.predict(input=small_query.format(message=message)):
                    partial_response += chunk
                    full_response = partial_response
                    time.sleep(0.02)
                    yield partial_response
                
                self.memory_size = len(full_response)
                self.current_query += 1
        
        except Exception as e:
            yield f"Произошла ошибка: {e}. Повторите ваш запрос ещё раз или перезагрузите страницу."


def create_chatbot() -> ChatBot:
    """
    Создает и возвращает экземпляр чат-бота.

    Returns:
        ChatBot: Экземпляр класса ChatBot.
    """
    return ChatBot()

custom_css = """
/* Основные цвета и переменные */
:root {
    --body-background-fill: #2D3250;
    --primary-color: #2D3250;
    --secondary-color: #424769;
    --accent-color: #7077A1;
    --light-color: #F6B17A;
    --background-color: #1c3f6f;
    --chat-user-msg: #7077A1;
    --chat-bot-msg: #2D3250;
    --background-fill-secondary: #0c2139;
    --input-background-fill: #0c2139;
    --block-background-fill: #0c2139;
    --button-secondary-background-fill: #0c2139;
    --color-accent-soft: #1c3f6f;
}

.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
    padding: 20px !important;
    background-color: var(--background-color) !important;
    border-radius: 15px !important;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1) !important;
}
"""

demo = gr.ChatInterface(
    fn=create_chatbot().predict,
    title="🏠 Я умный ассистент по дизайну интерьера",
    description="💬 Задайте вопрос, и я помогу вам подобрать товары для интерьера и отвечу на ваши запросы по дизайну.",
    examples=[
        "Мне нужен диван в стиле минимализм для гостиной",
        "Посоветуй светильник для спальни в скандинавском стиле",
        "Какие есть варианты обеденного стола до 30000 рублей?"
    ],
    css=custom_css
)

if __name__ == "__main__":
    demo.launch(share=True)
