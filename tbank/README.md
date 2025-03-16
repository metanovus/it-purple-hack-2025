# House Maximum Assistant: Умный совет по интерьеру дома 🏠

<p align="center">
  <img src="https://i.ibb.co/w5FZKm1/2025-03-14-03-58-20.png" alt="Working demonstration"/>
  <img src="https://i.ibb.co/67rXL0h6/2025-03-14-03-55-40.png" alt="Working demonstration"/>
</p>

* Демонстрация проекта (деплой в облаке): [ссылка на Hugging Face Spaces (Gradio)](https://huggingface.co/spaces/metanovus/maximum-house-assistant).

Данный проект представляет собой разработку умного ассистента по дизайну интерьера, который помогает пользователям подбирать товары на основе их предпочтений и требований. Ассистент использует современные технологии обработки естественного языка и векторного поиска для предоставления релевантных рекомендаций.

## Использованные технологии ⚙️
<p align="center">
  <a href="https://go-skill-icons.vercel.app/">
    <img src="https://go-skill-icons.vercel.app/api/icons?i=linux,python,pycharm,qdrant,docker,gradio,huggingface,mistral&theme=dark"/>
  </a>
</p>

## Описание функционала 🚀

Ассистент способен:

* Определять потребности пользователя и его персональные предпочтения в области дизайна интерьеров (гостиная, кухня, спальня, ванная)
* Составлять оптимальный набор товаров под бюджет и потребности
* Корректировать предложения на основе обратной связи

## Структура проекта 📂

Проект состоит из следующих основных каталогов и файлов:

```
tbank/
├── notebook/
│   └── maximum-house-assistant.ipynb   # Ноутбук с пайплайном построения RAG-модели
├── .env                       # Файл с API-токенами для демонстрации проекта
├── app.py                     # Основной файл файл приложения в Gradio
├── requirements.txt           # Файл с зависимостями для проекта
└── Dockerfile                 # Dockerfile для контейнеризации проекта
``` 


## Установка ⚙️

Для установки проекта, клонируйте репозиторий и установите все необходимые зависимости:

```bash
git clone https://gitlab.atp-fivt.org/it-purple-hack/team198/tbank.git
cd tbank
```

### Запуск проекта в Docker 🐳

**Внимание:** так как проект использует Qdrant, то иногда Docker может не подключаться к базе. Рекомендовано для тестов использовать [задеплоенную](https://huggingface.co/spaces/metanovus/maximum-house-assistant) версию.

1. Постройте Docker-образ:

```bash
docker build -t tbank-house-designer:latest .
```

3. Запустите контейнер:

```bash
docker run --env-file .env -p 7860:7860 maximum-house-assistant:latest
```

Контейнер будет запущен на порту 7860, и вы сможете получить доступ к приложению через браузер по адресу [http://localhost:7860](http://localhost:7860).

## Запуск без Docker ▶️

Если вы не используете Docker, вы можете перейти по ссылке на Hugging Face Spaces (рекомендованный вариант):

* [Ссылка](https://huggingface.co/spaces/metanovus/maximum-house-assistant).
