#!/usr/bin/env python3
"""
Скрипт для переключения настроек корреляции
"""

import os
import sys

def toggle_btc_correlation():
    """Переключает настройку BTC-корреляции"""
    config_file = "config.py"
    
    if not os.path.exists(config_file):
        print("❌ Файл config.py не найден!")
        return
    
    # Читаем файл
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Определяем текущее состояние
    current_state = "ENABLE_BTC_CORRELATION_CHECK = True" in content
    
    if current_state:
        # Отключаем
        new_content = content.replace(
            "ENABLE_BTC_CORRELATION_CHECK = True",
            "ENABLE_BTC_CORRELATION_CHECK = False"
        )
        action = "отключена"
    else:
        # Включаем
        new_content = content.replace(
            "ENABLE_BTC_CORRELATION_CHECK = False", 
            "ENABLE_BTC_CORRELATION_CHECK = True"
        )
        action = "включена"
    
    # Записываем изменения
    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ BTC-корреляция {action}")
    print(f"📁 Изменения сохранены в {config_file}")

def show_current_settings():
    """Показывает текущие настройки корреляции"""
    try:
        from config import ENABLE_BTC_CORRELATION_CHECK, MAX_BTC_CORRELATED_POSITIONS
        print("📊 Текущие настройки корреляции:")
        print(f"   ENABLE_BTC_CORRELATION_CHECK = {ENABLE_BTC_CORRELATION_CHECK}")
        print(f"   MAX_BTC_CORRELATED_POSITIONS = {MAX_BTC_CORRELATED_POSITIONS}")
        
        if ENABLE_BTC_CORRELATION_CHECK:
            print("⚠️  ВНИМАНИЕ: BTC-корреляция включена - может блокировать 90% сделок!")
            print("💡 Рекомендация: отключите для более гибкой торговли")
        else:
            print("✅ BTC-корреляция отключена - гибкая торговля")
            
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")

def test_correlation():
    """Тестирует работу корреляций"""
    try:
        from correlation import check_correlation_risk
        
        print("\n🧪 Тест корреляций:")
        
        # Тест 1: Пустой портфель
        print("1. Пустой портфель:")
        print(f"   ETHUSDT: {check_correlation_risk('ETHUSDT', {})}")
        
        # Тест 2: С BTC
        print("2. С BTCUSDT:")
        print(f"   ETHUSDT: {check_correlation_risk('ETHUSDT', {'BTCUSDT': {}})}")
        print(f"   DOGEUSDT: {check_correlation_risk('DOGEUSDT', {'BTCUSDT': {}})}")
        
        # Тест 3: Внутри группы
        print("3. Внутри группы ETH:")
        print(f"   ETHUSD: {check_correlation_risk('ETHUSD', {'ETHUSDT': {}})}")
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")

if __name__ == "__main__":
    print("🔧 Управление настройками корреляции")
    print("=" * 50)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "toggle":
            toggle_btc_correlation()
        elif command == "test":
            test_correlation()
        elif command == "show":
            show_current_settings()
        else:
            print("❌ Неизвестная команда. Используйте: toggle, test, show")
    else:
        # Показываем меню
        show_current_settings()
        print("\n📋 Доступные команды:")
        print("   python toggle_correlation.py toggle  - переключить BTC-корреляцию")
        print("   python toggle_correlation.py test   - протестировать корреляции")
        print("   python toggle_correlation.py show   - показать настройки")
