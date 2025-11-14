#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов.
Этап 5: Визуализация графа зависимостей через Graphviz в SVG.
"""
import tempfile  # временные файлы
import subprocess  # запуск внешних команд
import shutil  # проверка наличия бинарей в PATH
from pathlib import Path  # удобная работа с путями


import json
import urllib.request
import urllib.error
import sys
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import ssl
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional, List, Set
from collections import defaultdict

class ConfigError(Exception):
    """Исключение для ошибок конфигурации."""
    pass

class ConfigReader:
    """Класс для чтения и валидации конфигурационного файла."""
    
    def __init__(self, config_path: str = "config.xml"):
        self.config_path = Path(config_path)
        self.config: Dict[str, str] = {}
    
    def read_config(self) -> Dict[str, str]:
        """
        Читает конфигурационный файл и возвращает словарь параметров.
        
        Returns:
            Dict[str, str]: Словарь с параметрами конфигурации.
        
        Raises:
            ConfigError: Если файл не найден или содержит ошибки.
        """
        if not self.config_path.exists():
            raise ConfigError(f"Конфигурационный файл не найден: {self.config_path}")
        
        try:
            tree = ET.parse(self.config_path)
            root = tree.getroot()
        except ET.ParseError as e:
            raise ConfigError(f"Ошибка парсинга XML: {e}")
        except Exception as e:
            raise ConfigError(f"Ошибка чтения файла: {e}")
        
        # Извлекаем параметры
        package_name = self._get_element_text(root, "package_name")
        repository_url = self._get_element_text(root, "repository_url")
        test_mode = self._get_element_text(root, "test_mode", default="false")
        test_repository_path = self._get_element_text(root, "test_repository_path", default="")
        output_file = self._get_element_text(root, "output_file")
        
        # Валидация параметров
        self._validate_package_name(package_name)
        self._validate_repository_url(repository_url, test_mode)
        self._validate_test_mode(test_mode)
        self._validate_test_repository_path(test_repository_path, test_mode)
        self._validate_output_file(output_file)
        
        self.config = {
            "package_name": package_name,
            "repository_url": repository_url,
            "test_mode": test_mode.lower(),
            "test_repository_path": test_repository_path,
            "output_file": output_file
        }
        
        return self.config
    
    def _get_element_text(self, root: ET.Element, tag: str, default: Optional[str] = None) -> str:
        """Извлекает текст элемента или возвращает значение по умолчанию."""
        element = root.find(tag)
        if element is None:
            if default is not None:
                return default
            raise ConfigError(f"Отсутствует обязательный параметр: {tag}")
        text = element.text
        return text.strip() if text else (default or "")
    
    def _validate_package_name(self, package_name: str) -> None:
        """Валидирует имя пакета."""
        if not package_name:
            raise ConfigError("Имя пакета не может быть пустым")
        if not package_name.replace("_", "").replace("-", "").isalnum():
            raise ConfigError(f"Некорректное имя пакета: {package_name}")
    
    def _validate_repository_url(self, repository_url: str, test_mode: str) -> None:
        """Валидирует URL репозитория."""
        if test_mode.lower() != "true":
            if not repository_url:
                raise ConfigError("URL репозитория не может быть пустым в обычном режиме")
            if not (repository_url.startswith("http://") or repository_url.startswith("https://")):
                raise ConfigError(f"Некорректный URL репозитория: {repository_url}")
    
    def _validate_test_mode(self, test_mode: str) -> None:
        """Валидирует режим тестирования."""
        test_mode_lower = test_mode.lower()
        if test_mode_lower not in ("true", "false"):
            raise ConfigError(f"Некорректное значение test_mode: {test_mode}. Допустимые значения: true, false")
    
    def _validate_test_repository_path(self, test_repository_path: str, test_mode: str) -> None:
        """Валидирует путь к тестовому репозиторию."""
        if test_mode.lower() == "true":
            if not test_repository_path:
                raise ConfigError("Путь к тестовому репозиторию обязателен в тестовом режиме")
            path = Path(test_repository_path)
            if not path.exists():
                raise ConfigError(f"Файл тестового репозитория не найден: {test_repository_path}")
    
    def _validate_output_file(self, output_file: str) -> None:
        """Валидирует имя выходного файла."""
        if not output_file:
            raise ConfigError("Имя выходного файла не может быть пустым")
        # Проверяем расширение файла
        if not output_file.endswith(('.svg', '.png', '.jpg', '.jpeg', '.pdf')):
            raise ConfigError(f"Некорректное расширение выходного файла: {output_file}")

class DependencyError(Exception):
    """Исключение для ошибок получения зависимостей."""
    pass

class CargoDependencyReader:
    """Чтение зависимостей пакета Rust через crates.io API с логами и защитой от зависаний."""

    def __init__(self):
        self.cache: dict[str, list[str]] = {}

    def get_dependencies(self, package_name: str) -> list[str]:
        package_name_lower = package_name.lower()
        if package_name_lower in self.cache:
            return self.cache[package_name_lower]

        url = f"https://crates.io/api/v1/crates/{package_name_lower}"
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.load(response)
        except urllib.error.HTTPError as e:
            raise DependencyError(f"Crate {package_name} не найден на crates.io: {e.code}")
        except Exception as e:
            raise DependencyError(f"Ошибка сети при получении {package_name}: {e}")

        versions = data.get("versions", [])
        if not versions:
            print(f"[CargoDependencyReader] Пакет {package_name} не содержит версий, зависимостей нет")
            self.cache[package_name_lower] = []
            return []

        # Берем самую последнюю версию
        latest_version = versions[0]
        deps_url = f"https://crates.io/api/v1/crates/{package_name_lower}/{latest_version['num']}/dependencies"
        try:
            req = urllib.request.Request(deps_url)
            req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                                         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=10) as response:
                deps_data = json.load(response)
        except Exception as e:
            raise DependencyError(f"Ошибка при получении зависимостей {package_name}: {e}")

        dependencies = []
        for dep in deps_data.get("dependencies", []):
            if dep.get("kind") in (None, "normal"):  # normal = обычная зависимость
                dep_name = dep.get("crate_id")
                if dep_name:
                    dependencies.append(dep_name)

    
        self.cache[package_name_lower] = dependencies
        return dependencies
class TestRepositoryReader:
    """Класс для чтения тестового репозитория из файла."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.graph: Dict[str, List[str]] = {}
    
    def read_graph(self) -> Dict[str, List[str]]:
        """
        Читает граф зависимостей из файла.
        
        Формат файла:
        A: B, C
        B: D
        C: D
        D: E
        
        Returns:
            Dict[str, List[str]]: Граф зависимостей (пакет -> список зависимостей).
        
        Raises:
            DependencyError: Если файл не найден или содержит ошибки.
        """
        if not self.file_path.exists():
            raise DependencyError(f"Файл тестового репозитория не найден: {self.file_path}")
        
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            raise DependencyError(f"Ошибка чтения файла тестового репозитория: {e}")
        
        self.graph = {}
        lines = content.strip().split('\n')
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            # Пропускаем пустые строки и комментарии
            if not line or line.startswith('#'):
                continue
            
            # Формат: PACKAGE: DEP1, DEP2, DEP3
            if ':' not in line:
                raise DependencyError(f"Некорректный формат строки {line_num}: {line}")
            
            parts = line.split(':', 1)
            package = parts[0].strip()
            deps_str = parts[1].strip()
            
            # Валидация имени пакета (большие латинские буквы)
            if not package.isupper() or not package.isalpha():
                raise DependencyError(f"Некорректное имя пакета на строке {line_num}: {package}. "
                                   f"Используйте большие латинские буквы.")
            
            # Парсим зависимости
            dependencies = []
            if deps_str:
                deps = [d.strip() for d in deps_str.split(',')]
                for dep in deps:
                    if dep:
                        # Валидация имени зависимости
                        if not dep.isupper() or not dep.isalpha():
                            raise DependencyError(f"Некорректное имя зависимости на строке {line_num}: {dep}. "
                                                 f"Используйте большие латинские буквы.")
                        dependencies.append(dep)
            
            self.graph[package] = dependencies
        
        return self.graph
    
    def get_dependencies(self, package_name: str) -> List[str]:
        """
        Получает прямые зависимости пакета из тестового графа.
        
        Args:
            package_name: Имя пакета.
        
        Returns:
            List[str]: Список зависимостей.
        """
        return self.graph.get(package_name.upper(), [])

class DependencyGraph:
    """Класс для построения и работы с графом зависимостей."""
    
    def __init__(self):
        self.graph: Dict[str, List[str]] = defaultdict(list)
        self.all_packages: Set[str] = set()
        self.cycles: List[List[str]] = []
    
    def add_dependency(self, package: str, dependency: str) -> None:
        """Добавляет зависимость в граф."""
        self.graph[package].append(dependency)
        self.all_packages.add(package)
        self.all_packages.add(dependency)
    
    def build_graph_dfs(self, root_package: str, dependency_reader) -> None:
        """
        Строит граф зависимостей используя DFS с рекурсией.
        
        Args:
            root_package: Корневой пакет для построения графа.
            dependency_reader: Объект для получения зависимостей (CargoDependencyReader или TestRepositoryReader).
        """
        visited: Set[str] = set()
        recursion_stack: Set[str] = set()
        current_path: List[str] = []
        
        def dfs(package: str) -> None:
            """Рекурсивная функция DFS для обхода графа."""
            if package in recursion_stack:
                # Обнаружен цикл
                cycle_start = current_path.index(package)
                cycle = current_path[cycle_start:] + [package]
                if cycle not in self.cycles:
                    self.cycles.append(cycle)
                return
            
            if package in visited:
                return
            
            visited.add(package)
            recursion_stack.add(package)
            current_path.append(package)
            
            try:
                dependencies = dependency_reader.get_dependencies(package)
                for dep in dependencies:
                    self.add_dependency(package, dep)
                    dfs(dep)
            except DependencyError:
                # Если не удалось получить зависимости, просто пропускаем
                pass
            
            recursion_stack.remove(package)
            current_path.pop()
        
        dfs(root_package)
    
    def get_all_dependencies(self, package: str) -> Set[str]:
        """
        Получает все транзитивные зависимости пакета.
        
        Args:
            package: Имя пакета.
        
        Returns:
            Set[str]: Множество всех зависимостей (включая транзитивные).
        """
        visited: Set[str] = set()
        
        def collect_deps(pkg: str) -> None:
            if pkg in visited:
                return
            visited.add(pkg)
            for dep in self.graph.get(pkg, []):
                collect_deps(dep)
        
        for dep in self.graph.get(package, []):
            collect_deps(dep)
        
        return visited
    
    def has_cycles(self) -> bool:
        """Проверяет наличие циклов в графе."""
        return len(self.cycles) > 0
    
    def get_cycles(self) -> List[List[str]]:
        """Возвращает список всех найденных циклов."""
        return self.cycles
    
    def get_all_nodes(self) -> Set[str]:
        """Возвращает все узлы графа."""
        return self.all_packages.copy()
    
    def get_load_order(self, root_package: str) -> List[str]:
        """
        Получает порядок загрузки зависимостей для заданного пакета.
        
        Использует топологическую сортировку для определения порядка,
        в котором должны быть загружены зависимости (зависимости загружаются
        перед пакетами, которые от них зависят).
        
        Args:
            root_package: Корневой пакет.
        
        Returns:
            List[str]: Список пакетов в порядке загрузки.
        
        Raises:
            DependencyError: Если в графе есть циклы (топологическая сортировка невозможна).
        """
        if self.has_cycles():
            raise DependencyError("Невозможно определить порядок загрузки: обнаружены циклические зависимости")
        
        # Строим обратный граф (incoming edges) для топологической сортировки
        in_degree: Dict[str, int] = defaultdict(int)
        reverse_graph: Dict[str, List[str]] = defaultdict(list)
        
        # Инициализируем все узлы
        all_nodes = self.get_all_nodes()
        all_nodes.add(root_package)
        for node in all_nodes:
            in_degree[node] = 0
        
        # Строим обратный граф и считаем in-degree
        for package, deps in self.graph.items():
            for dep in deps:
                reverse_graph[dep].append(package)
                in_degree[package] += 1
        
        # Алгоритм Kahn для топологической сортировки
        queue: List[str] = []
        result: List[str] = []
        
        # Находим все узлы без входящих рёбер (листья графа)
        for node in all_nodes:
            if in_degree[node] == 0:
                queue.append(node)
        
        while queue:
            # Сортируем для детерминированного порядка
            queue.sort()
            node = queue.pop(0)
            result.append(node)
            
            # Уменьшаем in-degree для всех зависимых пакетов
            for dependent in reverse_graph[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        # Проверяем, что все узлы обработаны
        if len(result) != len(all_nodes):
            # Это не должно произойти, если нет циклов, но на всякий случай
            remaining = all_nodes - set(result)
            raise DependencyError(f"Не удалось определить порядок загрузки для узлов: {remaining}")
        
        return result
    
    def to_dot(self, root_package: str) -> str:
        """
        Генерирует текстовое представление графа на языке диаграмм Graphviz (DOT).
        
        Args:
            root_package: Корневой пакет для выделения в графе.
        
        Returns:
            str: DOT представление графа.
        """
        lines = ["digraph dependency_graph {"]
        lines.append("    rankdir=TB;")
        lines.append("    node [shape=box, style=rounded];")
        lines.append("")
        
        # Выделяем корневой пакет
        lines.append(f'    "{root_package}" [color=blue, fontcolor=blue, penwidth=2];')
        lines.append("")
        
        # Добавляем все узлы графа
        all_nodes = self.get_all_nodes()
        all_nodes.add(root_package)
        
        # Добавляем рёбра графа
        for package, deps in self.graph.items():
            for dep in deps:
                # Выделяем циклы красным цветом
                is_cycle = False
                for cycle in self.cycles:
                    if package in cycle and dep in cycle:
                        is_cycle = True
                        break
                
                if is_cycle:
                    lines.append(f'    "{package}" -> "{dep}" [color=red, penwidth=2];')
                else:
                    lines.append(f'    "{package}" -> "{dep}";')
        
        # Добавляем изолированные узлы (без зависимостей и не являющиеся зависимостями)
        isolated = all_nodes - set(self.graph.keys())
        isolated = isolated - {dep for deps in self.graph.values() for dep in deps}
        for node in isolated:
            if node != root_package:
                lines.append(f'    "{node}";')
        
        lines.append("}")
        return "\n".join(lines)
    
    def save_svg(self, root_package: str, output_file: str) -> None:
        # Сохраняет изображение графа в формате SVG, пытаясь несколько стратегий:
        # 1) системный `dot` (Graphviz),
        # 2) python-graphviz (.pipe),
        # 3) если ничего нет — сохраняет .dot и выдаёт понятную ошибку.
        # Генерируем DOT из текущего графа (вызов существующего метода)
        dot_content = self.to_dot(root_package)  # строка DOT

        # Создаём временный DOT файл, чтобы dot мог его прочитать (если понадобится)
        tmp_dot = None  # переменная для пути временного файла
        try:
            # Открываем временный файл для записи DOT-контента
            tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False, encoding='utf-8')
            tmp_dot = tmp.name  # сохраняем путь к файлу
            tmp.write(dot_content)  # записываем DOT в файл
            tmp.close()  # закрываем файл (dot/graphviz будет читать файл по пути)

            # Проверяем наличие системного исполняемого файла 'dot' в PATH
            dot_exe = shutil.which('dot')  # путь к dot или None
            if dot_exe:
                # Если dot найден, то пытаемся вызвать его для генерации SVG
                # Формируем команду: dot -Tsvg tmp_dot -o output_file
                cmd = [dot_exe, '-Tsvg', tmp_dot, '-o', output_file]
                # Запускаем команду, ограничиваем время выполнения, собираем stdout/stderr
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                # Если команда завершилась с ошибкой, выбрасываем DependencyError с текстом
                if proc.returncode != 0:
                    # Если dot вернул ошибку — поднимаем понятное исключение с stderr
                    raise DependencyError(f"Graphviz (dot) завершился с ошибкой: {proc.stderr.strip()}")
                # Успешно сгенерировали SVG через dot — возвращаемся
                return

            # Если dot не найден — пробуем python-библиотеку graphviz
            try:
                import graphviz  # попытка импортировать библиотеку graphviz
            except Exception as e:
                graphviz = None  # если не получилось — отметим, что библиотека недоступна

            if graphviz:
                try:
                    # Используем graphviz.Source и pipe(format='svg') -> получаем байты SVG
                    gv = graphviz.Source(dot_content)  # создаём источник графа
                    svg_bytes = gv.pipe(format='svg')  # получаем SVG в виде байтов
                    # Записываем байты в выходной файл
                    with open(output_file, 'wb') as f_out:
                        f_out.write(svg_bytes)
                    # Успешно сгенерировали SVG через python-graphviz
                    return
                except Exception as e:
                    # Если graphviz-python не смог отрендерить (часто из-за отсутствия бэкенда),
                    # мы падаем в следующий блок, где сохраним .dot и сообщим, что делать.
                    pass

            # Если мы сюда попали — ни dot, ни graphviz-python не помогли.
            # Сохраняем .dot рядом с желаемым output_file и даём инструкцию, как вручную получить SVG.
            dot_file_fallback = Path(output_file).with_suffix('.dot')  # путь к файлу .dot
            # Копируем временный .dot в dot_file_fallback (перезаписываем при необходимости)
            try:
                # Читаем временный файл и записываем в целевой .dot
                with open(tmp_dot, 'r', encoding='utf-8') as src, open(dot_file_fallback, 'w', encoding='utf-8') as dst:
                    dst.write(src.read())
            except Exception:
                # Если копирование по какой-то причине не удалось, всё равно попробуем записать напрямую
                with open(dot_file_fallback, 'w', encoding='utf-8') as dst:
                    dst.write(dot_content)

            # Выдаём понятный DependencyError с инструкцией для пользователя
            raise DependencyError(
                "Невозможно автоматически сгенерировать SVG: не найден исполняемый 'dot' и/или не работает python-библиотека 'graphviz'.\n"
                f"Файл с описанием графа сохранён как: {dot_file_fallback}\n\n"
                "Установите Graphviz (системный бинарный 'dot'), например:\n"
                "  Windows: скачайте и установите с https://graphviz.org/download/ (добавьте папку bin в PATH)\n"
                "  macOS: brew install graphviz\n"
                "  Linux: sudo apt-get install graphviz\n\n"
                "После установки выполните вручную:\n"
                f"  dot -Tsvg {dot_file_fallback} -o {output_file}\n\n"
                "Либо установите python-библиотеку graphviz и обеспечьте доступность бэкенда:\n"
                "  pip install graphviz\n"
            )

        finally:
            # В finally пытаемся удалить временный файл .dot, если он был создан
            try:
                if tmp_dot:
                    Path(tmp_dot).unlink()
            except Exception:
                # Игнорируем ошибки удаления — файл временный, пользователь может потереть вручную
                pass
def print_config(config: Dict[str, str]) -> None:
    print("Параметры конфигурации:\n")
    for key, value in config.items():
        print(f"{key}: {value}")

def print_dependencies(package_name: str, dependencies: List[str]) -> None:
    print(f"Прямые зависимости пакета '{package_name}':\n")
    if dependencies:
        for i, dep in enumerate(dependencies, 1):
            print(f"{i}. {dep}")
    else:
        print("Зависимости не найдены")

def print_graph_info(graph: DependencyGraph, root_package: str) -> None:
    print(f"Граф зависимостей для пакета '{root_package}':\n")
    
    all_deps = graph.get_all_dependencies(root_package)
    print(f"\nВсего зависимостей (включая транзитивные): {len(all_deps)}")
    if all_deps:
        print("Список всех зависимостей:")
        for i, dep in enumerate(sorted(all_deps), 1):
            print(f"  {i}. {dep}")
    
    if graph.has_cycles():
        print(f"\nОбнаружены циклические зависимости: {len(graph.get_cycles())}")
        for i, cycle in enumerate(graph.get_cycles(), 1):
            cycle_str = " -> ".join(cycle)
            print(f"  Цикл {i}: {cycle_str}")
    else:
        print("\nЦиклических зависимостей не обнаружено")
    

def print_load_order(graph: DependencyGraph, root_package: str) -> None:
    print(f"Порядок загрузки зависимостей для пакета '{root_package}':\n")
    
    try:
        load_order = graph.get_load_order(root_package)
        
        print(f"\nВсего пакетов для загрузки: {len(load_order)}")
        print("\nПорядок загрузки:")
        for i, package in enumerate(load_order, 1):
            marker = " ← корневой" if package == root_package else ""
            print(f"  {i}. {package}{marker}")
        
    except DependencyError as e:
        print(f"\n {e}")
        print("Порядок загрузки не может быть определен из-за циклических зависимостей.")
    

def main():
    """Главная функция приложения."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.xml"
    
    try:
        # Чтение конфигурации
        reader = ConfigReader(config_path)
        config = reader.read_config()
        print_config(config)
        
        package_name = config["package_name"]
        
        # Этап 3: Построение графа зависимостей
        dependency_graph = DependencyGraph()
        
        if config["test_mode"] == "true":
            # Тестовый режим: читаем из файла
            test_file_path = config["test_repository_path"]
            print(f"\nЧтение тестового репозитория из файла: {test_file_path}")
            test_reader = TestRepositoryReader(test_file_path)
            test_reader.read_graph()
            
            # Выводим прямые зависимости (для совместимости с этапом 2)
            dependencies = test_reader.get_dependencies(package_name)
            print_dependencies(package_name, dependencies)
            
            # Строим граф с помощью DFS
            print(f"\nПостроение графа зависимостей для пакета '{package_name}'...")
            dependency_graph.build_graph_dfs(package_name, test_reader)
        else:
            # Обычный режим: получаем из GitHub
            repository_url = config["repository_url"]
            print(f"\nПолучение зависимостей для пакета '{package_name}'...")
            cargo_reader = CargoDependencyReader()
            
            # Выводим прямые зависимости (для совместимости с этапом 2)
            dependencies = cargo_reader.get_dependencies(package_name)
            print_dependencies(package_name, dependencies)
            
            # Строим граф с помощью DFS
            print(f"\nПостроение графа зависимостей для пакета '{package_name}'...")
            dependency_graph.build_graph_dfs(package_name, cargo_reader)
        
        # Выводим информацию о графе
        print_graph_info(dependency_graph, package_name)
        
        # Этап 4: Порядок загрузки зависимостей
        print_load_order(dependency_graph, package_name)
        
        # Этап 5: Визуализация графа
        output_file = config["output_file"]
        print(f"\nГенерация визуализации графа...")
        try:
            dependency_graph.save_svg(package_name, output_file)
            print(f"Визуализация сохранена в файл: {output_file}")
            
            # Выводим DOT представление для справки
            dot_content = dependency_graph.to_dot(package_name)
            dot_file = output_file.replace('.svg', '.dot')
            with open(dot_file, 'w', encoding='utf-8') as f:
                f.write(dot_content)
            print(f"DOT представление сохранено в файл: {dot_file}")
        except DependencyError as e:
            print(f"{e}")
            # Сохраняем хотя бы DOT файл
            dot_content = dependency_graph.to_dot(package_name)
            dot_file = output_file.replace('.svg', '.dot')
            with open(dot_file, 'w', encoding='utf-8') as f:
                f.write(dot_content)
            print(f"DOT представление сохранено в файл: {dot_file}")
            print("  Для генерации SVG установите Graphviz и запустите:")
            print(f"  dot -Tsvg {dot_file} -o {output_file}")
        
    except ConfigError as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        sys.exit(1)
    except DependencyError as e:
        print(f"Ошибка получения зависимостей: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()


