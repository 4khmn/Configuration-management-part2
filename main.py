#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов.
Этап 5: Визуализация графа зависимостей через Graphviz в SVG.
"""
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
    """Выводит информацию о построенном графе зависимостей."""
    print("\n")
    print(f"Граф зависимостей для пакета '{root_package}':")
    
    all_deps = graph.get_all_dependencies(root_package)
    print(f"\nВсего зависимостей (включая транзитивные): {len(all_deps)}")
    if all_deps:
        print("Список всех зависимостей:")
        for i, dep in enumerate(sorted(all_deps), 1):
            print(f"  {i}. {dep}")
    
    if graph.has_cycles():
        print(f"\n  Обнаружены циклические зависимости: {len(graph.get_cycles())}")
        for i, cycle in enumerate(graph.get_cycles(), 1):
            cycle_str = " -> ".join(cycle)
            print(f"  Цикл {i}: {cycle_str}")
    else:
        print("\n Циклических зависимостей не обнаружено")

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


