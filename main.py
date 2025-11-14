#!/usr/bin/env python3
"""
Инструмент визуализации графа зависимостей для менеджера пакетов.
Этап 1: Минимальный прототип с конфигурацией.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional


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


def print_config(config: Dict[str, str]) -> None:
    """Выводит все параметры конфигурации в формате ключ-значение."""
    print("=" * 50)
    print("Параметры конфигурации:")
    print("=" * 50)
    for key, value in config.items():
        print(f"{key}: {value}")
    print("=" * 50)


def main():
    """Главная функция приложения."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.xml"
    
    try:
        reader = ConfigReader(config_path)
        config = reader.read_config()
        print_config(config)
    except ConfigError as e:
        print(f"Ошибка конфигурации: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

