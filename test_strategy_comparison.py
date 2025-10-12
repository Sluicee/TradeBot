"""
Скрипт для сравнительного тестирования стратегий:
1. Baseline (без Kelly и Averaging)
2. Kelly Only (только Kelly Criterion)
3. Averaging Only (только умное докупание)
4. Combined (Kelly + Averaging)

Использование:
    python test_strategy_comparison.py
"""

import asyncio
import json
import os
from datetime import datetime
from backtest import run_backtest
from config import INITIAL_BALANCE

# Конфигурации для тестирования
TEST_CONFIGS = [
    {"name": "Baseline", "kelly": False, "averaging": False},
    {"name": "Kelly_Only", "kelly": True, "averaging": False},
    {"name": "Averaging_Only", "kelly": False, "averaging": True},
    {"name": "Combined", "kelly": True, "averaging": True},
]

# Параметры теста
TEST_SYMBOL = "BTCUSDT"
TEST_INTERVAL = "1h"
TEST_PERIOD_HOURS = 720  # 30 дней (месяц)
TEST_BALANCE = INITIAL_BALANCE

async def modify_config(use_kelly: bool, use_averaging: bool):
    """Временно изменяет config.py для теста"""
    config_path = "config.py"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified_lines = []
    for line in lines:
        if line.startswith("USE_KELLY_CRITERION = "):
            modified_lines.append(f"USE_KELLY_CRITERION = {use_kelly}\n")
        elif line.startswith("ENABLE_AVERAGING = "):
            modified_lines.append(f"ENABLE_AVERAGING = {use_averaging}\n")
        else:
            modified_lines.append(line)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        f.writelines(modified_lines)
    
    print(f"  [CONFIG] USE_KELLY_CRITERION={use_kelly}, ENABLE_AVERAGING={use_averaging}")

async def run_all_tests():
    """Запускает все тесты и собирает результаты"""
    
    print("\n" + "="*100)
    print("ЗАПУСК СРАВНИТЕЛЬНОГО ТЕСТИРОВАНИЯ СТРАТЕГИЙ")
    print("="*100)
    print(f"Символ: {TEST_SYMBOL}")
    print(f"Интервал: {TEST_INTERVAL}")
    print(f"Период: {TEST_PERIOD_HOURS} часов")
    print(f"Начальный баланс: ${TEST_BALANCE}")
    print("="*100 + "\n")
    
    results = []
    
    for i, config in enumerate(TEST_CONFIGS, 1):
        print(f"\n{'='*100}")
        print(f"[ТЕСТ {i}/4] {config['name']}")
        print(f"{'='*100}")
        
        # Модифицируем config.py
        await modify_config(config['kelly'], config['averaging'])
        
        # Перезагружаем модули для применения новых настроек
        import importlib
        import paper_trader
        importlib.reload(paper_trader)
        
        # Запускаем бэктест
        try:
            result = await run_backtest(
                symbol=TEST_SYMBOL,
                interval=TEST_INTERVAL,
                period_hours=TEST_PERIOD_HOURS,
                start_balance=TEST_BALANCE,
                use_statistical_models=False,
                enable_kelly=config['kelly'],
                enable_averaging=config['averaging']
            )
            
            if result:
                result['config_name'] = config['name']
                results.append(result)
                
                print(f"\n[OK] {config['name']} zavershyon uspeshno")
                print(f"    Pribyl: ${result['profit']:.2f} ({result['profit_percent']:.2f}%)")
                print(f"    Win Rate: {result['win_rate']:.2f}%")
                print(f"    Sdelok: {result['trades_count']}")
            else:
                print(f"\n[ERROR] {config['name']} ne vernul rezultat")
                
        except Exception as e:
            print(f"\n[ERROR] Oshibka pri vypolnenii {config['name']}: {e}")
            import traceback
            traceback.print_exc()
    
    # Сохраняем результаты
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = "backtests"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = os.path.join(output_dir, f"strategy_comparison_{timestamp}.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_params": {
                "symbol": TEST_SYMBOL,
                "interval": TEST_INTERVAL,
                "period_hours": TEST_PERIOD_HOURS,
                "start_balance": TEST_BALANCE,
                "timestamp": timestamp
            },
            "results": results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*100}")
    print(f"РЕЗУЛЬТАТЫ СОХРАНЕНЫ: {output_file}")
    print(f"{'='*100}\n")
    
    # Выводим сравнительную таблицу
    print_comparison_table(results)
    
    # Генерируем отчёт
    generate_report(results, timestamp)
    
    return results

def print_comparison_table(results):
    """Выводит сравнительную таблицу результатов"""
    
    print("\n" + "="*100)
    print("СРАВНИТЕЛЬНАЯ ТАБЛИЦА РЕЗУЛЬТАТОВ")
    print("="*100)
    
    if not results:
        print("Нет результатов для отображения")
        return
    
    # Заголовок
    print(f"{'Конфигурация':<20} {'Прибыль $':<15} {'Прибыль %':<15} {'Win Rate':<15} {'Сделок':<10} {'Sharpe':<10}")
    print("-"*100)
    
    # Данные
    for r in results:
        sharpe = r.get('sharpe_ratio', 0)
        print(f"{r['config_name']:<20} "
              f"${r['profit']:<14.2f} "
              f"{r['profit_percent']:<14.2f}% "
              f"{r['win_rate']:<14.2f}% "
              f"{r['trades_count']:<10} "
              f"{sharpe:<10.3f}")
    
    print("="*100 + "\n")
    
    # Определяем лучшую конфигурацию
    if results:
        best_profit = max(results, key=lambda x: x['profit'])
        best_sharpe = max(results, key=lambda x: x.get('sharpe_ratio', 0))
        best_winrate = max(results, key=lambda x: x['win_rate'])
        
        print("LUCHSHIE REZULTATY:")
        print(f"  * Maksimalnaya pribyl: {best_profit['config_name']} (${best_profit['profit']:.2f})")
        print(f"  * Luchshiy Sharpe Ratio: {best_sharpe['config_name']} ({best_sharpe.get('sharpe_ratio', 0):.3f})")
        print(f"  * Luchshiy Win Rate: {best_winrate['config_name']} ({best_winrate['win_rate']:.2f}%)")
        print()

def generate_report(results, timestamp):
    """Генерирует подробный отчёт в markdown"""
    
    report_file = f"backtests/STRATEGY_COMPARISON_REPORT_{timestamp}.md"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"# Отчёт: Сравнительное тестирование стратегий\n\n")
        f.write(f"**Дата**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Параметры тестирования\n\n")
        f.write(f"- **Символ**: {TEST_SYMBOL}\n")
        f.write(f"- **Интервал**: {TEST_INTERVAL}\n")
        f.write(f"- **Период**: {TEST_PERIOD_HOURS} часов (≈{TEST_PERIOD_HOURS//24} дней)\n")
        f.write(f"- **Начальный баланс**: ${TEST_BALANCE}\n\n")
        
        f.write(f"## Тестируемые конфигурации\n\n")
        for i, config in enumerate(TEST_CONFIGS, 1):
            f.write(f"{i}. **{config['name']}**\n")
            f.write(f"   - Kelly Criterion: {'✓' if config['kelly'] else '✗'}\n")
            f.write(f"   - Smart Averaging: {'✓' if config['averaging'] else '✗'}\n\n")
        
        f.write(f"## Результаты\n\n")
        f.write(f"| Конфигурация | Прибыль $ | Прибыль % | Win Rate | Сделок | Sharpe | Max DD |\n")
        f.write(f"|--------------|-----------|-----------|----------|--------|--------|--------|\n")
        
        for r in results:
            sharpe = r.get('sharpe_ratio', 0)
            max_dd = r.get('max_drawdown_percent', 0)
            f.write(f"| {r['config_name']} | ${r['profit']:.2f} | {r['profit_percent']:.2f}% | "
                   f"{r['win_rate']:.2f}% | {r['trades_count']} | {sharpe:.3f} | {max_dd:.2f}% |\n")
        
        f.write(f"\n## Детальный анализ\n\n")
        
        for r in results:
            f.write(f"### {r['config_name']}\n\n")
            f.write(f"**Финансовые результаты:**\n")
            f.write(f"- Финальный баланс: ${r['final_balance']:.2f}\n")
            f.write(f"- Прибыль: ${r['profit']:.2f} ({r['profit_percent']:+.2f}%)\n")
            f.write(f"- ROI: {r.get('roi_percent', r['profit_percent']):.2f}%\n\n")
            
            f.write(f"**Статистика сделок:**\n")
            f.write(f"- Всего сделок: {r['trades_count']}\n")
            f.write(f"- Выигрышных: {r.get('winning_trades', 0)}\n")
            f.write(f"- Проигрышных: {r.get('losing_trades', 0)}\n")
            f.write(f"- Win Rate: {r['win_rate']:.2f}%\n")
            f.write(f"- Средний выигрыш: {r.get('avg_win_percent', 0):.2f}%\n")
            f.write(f"- Средний проигрыш: {r.get('avg_loss_percent', 0):.2f}%\n\n")
            
            f.write(f"**Метрики риска:**\n")
            f.write(f"- Sharpe Ratio: {r.get('sharpe_ratio', 0):.3f}\n")
            f.write(f"- Maximum Drawdown: {r.get('max_drawdown_percent', 0):.2f}%\n")
            f.write(f"- Profit Factor: {r.get('profit_factor', 0):.2f}\n\n")
            
            f.write(f"**Триггеры:**\n")
            f.write(f"- Stop-Loss: {r.get('stop_loss_triggers', 0)}\n")
            f.write(f"- Take-Profit: {r.get('take_profit_triggers', 0)}\n")
            f.write(f"- Trailing Stop: {r.get('trailing_stop_triggers', 0)}\n\n")
        
        # Сравнение
        if len(results) > 1:
            baseline = next((r for r in results if r['config_name'] == 'Baseline'), None)
            
            if baseline:
                f.write(f"## Сравнение с Baseline\n\n")
                f.write(f"| Конфигурация | Δ Прибыль % | Δ Win Rate | Δ Sharpe |\n")
                f.write(f"|--------------|-------------|------------|-----------|\n")
                
                for r in results:
                    if r['config_name'] != 'Baseline':
                        delta_profit = r['profit_percent'] - baseline['profit_percent']
                        delta_wr = r['win_rate'] - baseline['win_rate']
                        delta_sharpe = r.get('sharpe_ratio', 0) - baseline.get('sharpe_ratio', 0)
                        
                        f.write(f"| {r['config_name']} | {delta_profit:+.2f}% | "
                               f"{delta_wr:+.2f}% | {delta_sharpe:+.3f} |\n")
        
        f.write(f"\n## Выводы\n\n")
        
        if results:
            best_profit = max(results, key=lambda x: x['profit'])
            best_sharpe = max(results, key=lambda x: x.get('sharpe_ratio', 0))
            best_winrate = max(results, key=lambda x: x['win_rate'])
            
            f.write(f"**Лучшие показатели:**\n\n")
            f.write(f"- 🏆 **Максимальная прибыль**: {best_profit['config_name']} "
                   f"(${best_profit['profit']:.2f}, {best_profit['profit_percent']:+.2f}%)\n")
            f.write(f"- 📊 **Лучший Sharpe Ratio**: {best_sharpe['config_name']} "
                   f"({best_sharpe.get('sharpe_ratio', 0):.3f})\n")
            f.write(f"- ✅ **Лучший Win Rate**: {best_winrate['config_name']} "
                   f"({best_winrate['win_rate']:.2f}%)\n\n")
            
            f.write(f"**Рекомендации:**\n\n")
            
            if best_profit['config_name'] == best_sharpe['config_name']:
                f.write(f"Конфигурация **{best_profit['config_name']}** показывает лучшие результаты "
                       f"как по прибыльности, так и по risk-adjusted returns (Sharpe Ratio). "
                       f"Рекомендуется для использования в live trading.\n\n")
            else:
                f.write(f"Конфигурация **{best_profit['config_name']}** даёт максимальную прибыль, "
                       f"но **{best_sharpe['config_name']}** имеет лучшее соотношение риск/доходность. "
                       f"Выбор зависит от risk appetite.\n\n")
    
    print(f"OTCHYOT SOKHRANYON: {report_file}\n")

if __name__ == "__main__":
    asyncio.run(run_all_tests())

