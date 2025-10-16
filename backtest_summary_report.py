#!/usr/bin/env python3
"""
Сводный отчет по результатам бэктестов
"""

import json
import os
import glob
from datetime import datetime

def analyze_backtest_results():
    """Анализ результатов всех бэктестов"""
    
    # Найти все JSON файлы с результатами бэктестов
    backtest_files = glob.glob("backtests/backtest_*_15m_*.json")
    
    if not backtest_files:
        print("Файлы бэктестов не найдены!")
        return
    
    print(f"АНАЛИЗ РЕЗУЛЬТАТОВ БЭКТЕСТОВ")
    print(f"Найдено файлов: {len(backtest_files)}")
    print("=" * 60)
    
    total_symbols = 0
    total_trades = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0.0
    total_roi = 0.0
    
    results = []
    
    for file_path in sorted(backtest_files):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверить, что data - это словарь, а не список
            if isinstance(data, list):
                print(f"Пропуск {file_path}: файл содержит список данных")
                continue
            
            # Извлечь символ из имени файла
            filename = os.path.basename(file_path)
            symbol = filename.split('_')[1]
            
            # Основные метрики
            start_balance = data.get('start_balance', 100.0)
            end_balance = data.get('end_balance', data.get('final_balance', 100.0))
            profit = data.get('profit', end_balance - start_balance)
            roi = data.get('profit_percent', (profit / start_balance) * 100 if start_balance > 0 else 0)
            
            trades_count = data.get('trades_count', 0)
            win_rate = data.get('win_rate', 0.0)
            
            # Подсчет винрейта
            wins = 0
            losses = 0
            if 'trades' in data and isinstance(data['trades'], list):
                for trade in data['trades']:
                    if isinstance(trade, str):
                        # Если trade - это строка, анализируем её содержимое
                        if "прибыль: +" in trade or "PARTIAL-TP" in trade:
                            wins += 1
                        elif "прибыль: -" in trade or "STOP-LOSS" in trade or "TRAILING-STOP" in trade:
                            losses += 1
                    elif isinstance(trade, dict):
                        # Если trade - это словарь
                        if trade.get('profit', 0) > 0:
                            wins += 1
                        elif trade.get('profit', 0) < 0:
                            losses += 1
            
            results.append({
                'symbol': symbol,
                'start_balance': start_balance,
                'end_balance': end_balance,
                'profit': profit,
                'roi': roi,
                'trades_count': trades_count,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate
            })
            
            total_symbols += 1
            total_trades += trades_count
            total_wins += wins
            total_losses += losses
            total_profit += profit
            total_roi += roi
            
            # Статус символа
            status_emoji = "+" if profit > 0 else "-" if profit < 0 else "="
            
            print(f"{status_emoji} {symbol:10} | "
                  f"Трейдов: {trades_count:2} | "
                  f"Винрейт: {win_rate:5.1f}% | "
                  f"ROI: {roi:+6.2f}% | "
                  f"P&L: ${profit:+7.2f}")
            
        except Exception as e:
            print(f"ОШИБКА при чтении {file_path}: {e}")
    
    print("=" * 60)
    
    # Общая статистика
    avg_roi = total_roi / total_symbols if total_symbols > 0 else 0
    overall_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0
    
    print(f"ОБЩАЯ СТАТИСТИКА:")
    print(f"   Символов: {total_symbols}")
    print(f"   Всего трейдов: {total_trades}")
    print(f"   Выигрышных: {total_wins}")
    print(f"   Проигрышных: {total_losses}")
    print(f"   Общий винрейт: {overall_win_rate:.1f}%")
    print(f"   Общий P&L: ${total_profit:+.2f}")
    print(f"   Средний ROI: {avg_roi:+.2f}%")
    
    # Топ и худшие символы
    profitable_symbols = [r for r in results if r['profit'] > 0]
    unprofitable_symbols = [r for r in results if r['profit'] < 0]
    
    print(f"\nТОП-3 ПРИБЫЛЬНЫХ СИМВОЛОВ:")
    top_profitable = sorted(profitable_symbols, key=lambda x: x['profit'], reverse=True)[:3]
    for i, result in enumerate(top_profitable, 1):
        print(f"   {i}. {result['symbol']:10} | ROI: {result['roi']:+6.2f}% | P&L: ${result['profit']:+7.2f}")
    
    print(f"\nТОП-3 УБЫТОЧНЫХ СИМВОЛОВ:")
    top_unprofitable = sorted(unprofitable_symbols, key=lambda x: x['profit'])[:3]
    for i, result in enumerate(top_unprofitable, 1):
        print(f"   {i}. {result['symbol']:10} | ROI: {result['roi']:+6.2f}% | P&L: ${result['profit']:+7.2f}")
    
    # Анализ активности
    active_symbols = [r for r in results if r['trades_count'] > 0]
    inactive_symbols = [r for r in results if r['trades_count'] == 0]
    
    print(f"\nАНАЛИЗ АКТИВНОСТИ:")
    print(f"   Активных символов: {len(active_symbols)}")
    print(f"   Неактивных символов: {len(inactive_symbols)}")
    
    if active_symbols:
        avg_trades = sum(r['trades_count'] for r in active_symbols) / len(active_symbols)
        print(f"   Среднее количество трейдов: {avg_trades:.1f}")
    
    # Сохранить детальный отчет
    report_data = {
        'timestamp': datetime.now().isoformat(),
        'total_symbols': total_symbols,
        'total_trades': total_trades,
        'total_wins': total_wins,
        'total_losses': total_losses,
        'overall_win_rate': overall_win_rate,
        'total_profit': total_profit,
        'avg_roi': avg_roi,
        'results': results
    }
    
    with open('backtest_summary_report.json', 'w', encoding='utf-8') as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    
    print(f"\nДетальный отчет сохранен в: backtest_summary_report.json")

if __name__ == "__main__":
    analyze_backtest_results()
