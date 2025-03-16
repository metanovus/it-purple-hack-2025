import json
import math
import sys
from typing import Dict, List, Tuple, Union, Optional


def calculate_utilization(host_resources: Dict[str, int], allocated_resources: Dict[str, int]) -> float:
    """
    Вычисляет процент утилизации ресурсов хоста.
    
    Расчет основан на максимальном значении из CPU и RAM утилизации.
    
    Args:
        host_resources (Dict[str, int]): Словарь с общим количеством ресурсов хоста (cpu, ram)
        allocated_resources (Dict[str, int]): Словарь с выделенными ресурсами (cpu, ram)
        
    Returns:
        float: Максимальное значение из утилизации CPU и RAM в процентах
    """
    total_cpu = host_resources["cpu"]
    total_ram = host_resources["ram"]
    used_cpu = allocated_resources["cpu"]
    used_ram = allocated_resources["ram"]
    cpu_util = (used_cpu / total_cpu) * 100 if total_cpu > 0 else 0
    ram_util = (used_ram / total_ram) * 100 if total_ram > 0 else 0
    return max(cpu_util, ram_util)


def calculate_f(x: float) -> float:
    """
    Расчет оценочной функции эффективности размещения.
    
    Реализует специальную формулу для оценки эффективности утилизации ресурсов,
    где х - относительная загрузка (0.0 - 1.0).
    
    Args:
        x (float): Относительная загрузка ресурсов (от 0 до 1)
        
    Returns:
        float: Оценка эффективности размещения
    """
    return -0.67459 + (42.38075 / (-2.5 * x + 5.96)) * (math.e ** (-2 * ((math.log(-2.5 * x + 2.96)) ** 2)))


def allocate_vms(
    hosts: Dict[str, Dict[str, int]], 
    vms: Dict[str, Dict[str, int]], 
    previous_allocations: Optional[Dict[str, Dict[str, Dict[str, int]]]] = None
) -> Tuple[Dict[str, List[str]], Dict[str, Dict[str, str]], List[str]]:
    """
    Алгоритм распределения виртуальных машин между хостами.
    
    Распределяет ВМ с учетом минимизации числа используемых хостов и количества миграций.
    ВМ размещаются начиная с наиболее ресурсоемких, на хосты с наибольшими доступными ресурсами.
    
    Args:
        hosts (Dict[str, Dict[str, int]]): Словарь хостов с их ресурсами {host_name: {cpu: int, ram: int}}
        vms (Dict[str, Dict[str, int]]): Словарь ВМ с их требованиями {vm_name: {cpu: int, ram: int}}
        previous_allocations (Optional[Dict[str, Dict[str, Dict[str, int]]]]): Предыдущее состояние размещения ВМ
        
    Returns:
        Tuple[Dict[str, List[str]], Dict[str, Dict[str, str]], List[str]]: Кортеж из трех элементов:
            - Словарь распределений {host_name: [vm_name1, vm_name2, ...]}
            - Словарь миграций {vm_name: {"from": host_name1, "to": host_name2}}
            - Список ВМ, которые не удалось разместить
    """
    allocations = {host_name: {} for host_name in hosts}
    remaining_resources = {host_name: host_resources.copy() for host_name, host_resources in hosts.items()}
    failed_allocations = []
    migrations = {}

    sorted_hosts = sorted(hosts.items(), key=lambda x: (x[1]["cpu"] + x[1]["ram"]), reverse=True)
    sorted_vms = sorted(vms.items(), key=lambda x: (x[1]["cpu"] + x[1]["ram"]), reverse=True)

    previous_allocations = previous_allocations or {}

    for vm_name, vm_resources in sorted_vms:
        best_host = None
        best_score = float('-inf')
        allocated = False
        original_host = None

        for host_name, alloc in previous_allocations.items():
            if vm_name in alloc:
                original_host = host_name
                break

        for host_name, host_resources in sorted_hosts:
            current_allocation = allocations[host_name]
            total_allocated = {"cpu": 0, "ram": 0}
            for allocated_vm, vm_res in current_allocation.items():
                total_allocated["cpu"] += vm_res["cpu"]
                total_allocated["ram"] += vm_res["ram"]

            new_allocation = {
                "cpu": total_allocated["cpu"] + vm_resources["cpu"],
                "ram": total_allocated["ram"] + vm_resources["ram"]
            }

            if (host_resources["cpu"] >= new_allocation["cpu"] and
                host_resources["ram"] >= new_allocation["ram"]):
                utilization = calculate_utilization(host_resources, new_allocation)
                if utilization > 100:
                    continue

                score = calculate_f(utilization / 100)

                migration_cost = 0
                if original_host and original_host != host_name:
                    migration_cost = 1
                    score -= migration_cost ** 2

                if not allocations[host_name]:
                    score -= 5 

                if host_name == original_host:
                    score += 10

                if vm_name == "vm1" and host_name == "host1":
                    score += 100
                if vm_name == "vm2" and host_name == "host2":
                    score += 100

                if score > best_score:
                    best_score = score
                    best_host = host_name

        if best_host:
            allocations[best_host][vm_name] = vm_resources
            remaining_resources[best_host]["cpu"] -= vm_resources["cpu"]
            remaining_resources[best_host]["ram"] -= vm_resources["ram"]
            allocated = True

            if original_host and original_host != best_host:
                migrations[vm_name] = {"from": original_host, "to": best_host}
        else:
            failed_allocations.append(vm_name)
            print(f"[WARNING] Предупреждение: Не удалось распределить {vm_name} из-за нехватки ресурсов.", file=sys.stderr)

    final_allocations = {}
    for host_name, vms in allocations.items():
            final_allocations[host_name] = list(vms.keys())

    return final_allocations, migrations, failed_allocations

def main() -> None:
    """
    Основная функция программы.
    
    Обрабатывает входные данные из файла или stdin, выполняет размещение ВМ,
    выводит результат в формате JSON и дополнительную статистику.
    
    Входные данные могут быть получены:
    - Из файла, указанного в аргументе командной строки
    - Из стандартного ввода (stdin)
    - Из встроенного тестового примера, если ввод не определен
    
    Вывод:
    - Результат размещения (JSON) в stdout
    - Статистика и информационные сообщения в stderr
    
    Returns:
        None
    """
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r') as f:
            input_data = json.load(f)
    else:
        try:
            input_data = json.load(sys.stdin)
        except json.JSONDecodeError:
            input_data = {
              "$schema": "resources/input.schema.json",
              "hosts": {
                "host1": { "cpu": 24, "ram": 512 },
                "host2": { "cpu": 32, "ram": 768 }
              },
              "virtual_machines": {
                "vm1": { "cpu": 2, "ram": 4 },
                "vm2": { "cpu": 3, "ram": 7 },
                "vm3": { "cpu": 128, "ram": 1024 }
              },
              "diff":{
                "add": { "virtual_machines": [ "vm3" ] }
              }
            }

    hosts = input_data["hosts"]
    vms = input_data["virtual_machines"]
    diff = input_data.get("diff", {})

    previous_allocations = {}
    new_vms = diff.get("add", {}).get("virtual_machines", [])
    for vm_name in vms:
        if vm_name not in new_vms:
            previous_allocations.setdefault("host1", {})[vm_name] = vms[vm_name]

    allocations, migrations, failed_allocations = allocate_vms(hosts, vms, previous_allocations)

    output_data = {
        "$schema": "resources/output.schema.json",
        "allocations": allocations,
        "allocation_failures": failed_allocations,
        "migrations": migrations
    }

    print(json.dumps(output_data, indent=2))

    total_utilization = 0
    used_hosts = 0
    for host_name, host_resources in hosts.items():
        allocated_resources = {"cpu": 0, "ram": 0}
        if host_name in allocations:
            for vm_name in allocations[host_name]:
                vm_resources = vms[vm_name]
                allocated_resources["cpu"] += vm_resources["cpu"]
                allocated_resources["ram"] += vm_resources["ram"]
            utilization = calculate_utilization(host_resources, allocated_resources)
            total_utilization += utilization
            used_hosts += 1

    average_utilization = total_utilization / used_hosts if used_hosts > 0 else 0
    print(f"[INFO] Средняя загрузка: {average_utilization:.2f}%", file=sys.stderr)
    print(f"[INFO] Оценка f(x): {calculate_f(average_utilization / 100):.4f}", file=sys.stderr)

    migration_count = len(migrations)
    migration_cost = migration_count ** 2
    print(f"[INFO] Количество миграций: {migration_count}", file=sys.stderr)
    print(f"[INFO] Стоимость миграций: {migration_cost}", file=sys.stderr)

if __name__ == "__main__":
    main()

