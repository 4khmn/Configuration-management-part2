#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов.
Этап 2: Сбор данных о зависимостях.
"""

import sys
import xml.etree.ElementTree as ET
import urllib.request
import urllib.error
import ssl
import re
from pathlib import Path
from typing import Dict, Optional, List


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
    """Класс для чтения зависимостей из Cargo.toml файлов."""
    
    def __init__(self, repository_url: str):
        self.repository_url = repository_url
        self.cargo_toml_content = ""
    
    def get_dependencies(self, package_name: str) -> List[str]:
        """
        Получает список прямых зависимостей для указанного пакета.
        
        Args:
            package_name: Имя пакета для анализа.
        
        Returns:
            List[str]: Список имен зависимостей.
        
        Raises:
            DependencyError: Если не удалось получить или распарсить зависимости.
        """
        # Пробуем сначала корневой Cargo.toml
        branch = "main"
        cargo_toml_url = self._get_cargo_toml_url(branch=branch)
        
        try:
            self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
            # Проверяем, не workspace ли это
            if '[workspace]' in self.cargo_toml_content:
                # Если workspace, ищем Cargo.toml в подпапке с именем пакета
                cargo_toml_url = self._get_cargo_toml_url(package_name, branch)
                self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
        except DependencyError as e:
            # Если не нашли в корне на main, пробуем master
            if branch == "main":
                branch = "master"
                cargo_toml_url = self._get_cargo_toml_url(branch=branch)
                try:
                    self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
                    # Проверяем workspace
                    if '[workspace]' in self.cargo_toml_content:
                        cargo_toml_url = self._get_cargo_toml_url(package_name, branch)
                        self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
                except DependencyError:
                    # Если не нашли в корне, пробуем в подпапке
                    try:
                        cargo_toml_url = self._get_cargo_toml_url(package_name, branch)
                        self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
                    except DependencyError:
                        raise e
            else:
                # Если не нашли в корне, пробуем в подпапке
                try:
                    cargo_toml_url = self._get_cargo_toml_url(package_name, branch)
                    self.cargo_toml_content = self._fetch_cargo_toml(cargo_toml_url)
                except DependencyError:
                    raise e
        
        try:
            dependencies = self._parse_dependencies()
            return dependencies
        except Exception as e:
            raise DependencyError(f"Ошибка парсинга зависимостей: {e}")
    
    def _get_cargo_toml_url(self, subpath: Optional[str] = None, branch: str = "main") -> str:
        """
        Преобразует URL репозитория в URL для получения Cargo.toml.
        
        Args:
            subpath: Опциональный подпуть (например, имя пакета для workspace).
            branch: Ветка репозитория (main или master).
        """
        # Поддерживаем GitHub репозитории
        # Формат: https://github.com/owner/repo
        github_match = re.match(r'https?://github\.com/([^/]+)/([^/]+)/?', self.repository_url)
        if github_match:
            owner = github_match.group(1)
            repo = github_match.group(2)
            # Убираем .git если есть
            repo = repo.rstrip('.git')
            # Формируем путь
            path = subpath + "/Cargo.toml" if subpath else "Cargo.toml"
            return f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        
        raise DependencyError(f"Неподдерживаемый формат URL репозитория: {self.repository_url}")
    
    def _fetch_cargo_toml(self, url: str) -> str:
        """Загружает содержимое Cargo.toml по URL."""
        try:
            # Пробуем сначала с проверкой сертификата
            ssl_context = None
            try:
                ssl_context = ssl.create_default_context()
            except Exception:
                pass
            
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Mozilla/5.0')
            
            try:
                if ssl_context:
                    response = urllib.request.urlopen(req, timeout=10, context=ssl_context)
                else:
                    response = urllib.request.urlopen(req, timeout=10)
            except ssl.SSLError:
                # Если SSL ошибка, используем небезопасный контекст (для разработки)
                ssl_context = ssl._create_unverified_context()
                response = urllib.request.urlopen(req, timeout=10, context=ssl_context)
            
            with response:
                content = response.read().decode('utf-8')
                return content
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Пробуем другую ветку
                if '/main/' in url:
                    url = url.replace('/main/', '/master/')
                    return self._fetch_cargo_toml(url)
                elif '/master/' in url:
                    # Если и master не работает, пробуем main
                    url = url.replace('/master/', '/main/')
                    return self._fetch_cargo_toml(url)
                raise DependencyError(f"Cargo.toml не найден в репозитории (404)")
            raise DependencyError(f"HTTP ошибка при получении Cargo.toml: {e.code}")
        except urllib.error.URLError as e:
            # Если это SSL ошибка, пробуем с небезопасным контекстом
            if 'SSL' in str(e) or 'CERTIFICATE' in str(e):
                try:
                    ssl_context = ssl._create_unverified_context()
                    req = urllib.request.Request(url)
                    req.add_header('User-Agent', 'Mozilla/5.0')
                    with urllib.request.urlopen(req, timeout=10, context=ssl_context) as response:
                        content = response.read().decode('utf-8')
                        return content
                except Exception as e2:
                    raise DependencyError(f"Ошибка сети при получении Cargo.toml: {e2}")
            raise DependencyError(f"Ошибка сети при получении Cargo.toml: {e}")
        except Exception as e:
            raise DependencyError(f"Неожиданная ошибка при получении Cargo.toml: {e}")
    
    def _parse_dependencies(self) -> List[str]:
        """
        Парсит зависимости из содержимого Cargo.toml.
        
        Обрабатывает форматы:
        - serde = "1.0"
        - tokio = { version = "1.0", features = ["full"] }
        - my-crate = { path = "../my-crate" }
        - [dependencies.serde]
        """
        dependencies = []
        lines = self.cargo_toml_content.split('\n')
        
        in_dependencies_section = False
        in_table_array = False
        
        for line in lines:
            line = line.strip()
            
            # Пропускаем комментарии
            if line.startswith('#') or not line:
                continue
            
            # Проверяем начало секции [dependencies]
            if line == '[dependencies]':
                in_dependencies_section = True
                in_table_array = False
                continue
            
            # Проверяем конец секции dependencies (начало новой секции)
            if line.startswith('[') and line != '[dependencies]':
                if in_dependencies_section and not in_table_array:
                    break
                in_dependencies_section = False
                in_table_array = False
                continue
            
            # Проверяем таблицы вида [dependencies.serde]
            table_match = re.match(r'\[dependencies\.([^\]]+)\]', line)
            if table_match:
                dep_name = table_match.group(1).strip('"\'')
                if dep_name not in dependencies:
                    dependencies.append(dep_name)
                in_dependencies_section = True
                in_table_array = True
                continue
            
            # Парсим зависимости в секции [dependencies]
            if in_dependencies_section:
                # Формат: name = "version" или name = { ... }
                dep_match = re.match(r'^([a-zA-Z0-9_-]+)\s*=', line)
                if dep_match:
                    dep_name = dep_match.group(1)
                    # Включаем все зависимости, включая те что с path
                    # (для этапа 2 нужно показать все прямые зависимости)
                    if dep_name not in dependencies:
                        dependencies.append(dep_name)
        
        return sorted(dependencies)


def print_config(config: Dict[str, str]) -> None:
    print("Параметры конфигурации:\n")
    for key, value in config.items():
        print(f"{key}: {value}")


def print_dependencies(package_name: str, dependencies: List[str]) -> None:
    print(f"Прямые зависимости пакета '{package_name}':")
    if dependencies:
        for i, dep in enumerate(dependencies, 1):
            print(f"{i}. {dep}")
    else:
        print("Зависимости не найдены")


def main():
    """Главная функция приложения."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.xml"
    
    try:
        # Чтение конфигурации
        reader = ConfigReader(config_path)
        config = reader.read_config()
        print_config(config)
        
        # Этап 2: Получение зависимостей (только если не тестовый режим)
        if config["test_mode"] != "true":
            package_name = config["package_name"]
            repository_url = config["repository_url"]
            
            print(f"\nПолучение зависимостей для пакета '{package_name}'...")
            dependency_reader = CargoDependencyReader(repository_url)
            dependencies = dependency_reader.get_dependencies(package_name)
            print_dependencies(package_name, dependencies)
        
    except ConfigError as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        sys.exit(1)
    except DependencyError as e:
        print(f"Ошибка получения зависимостей: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

