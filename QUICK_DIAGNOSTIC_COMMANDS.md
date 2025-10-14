# ⚡ БЫСТРАЯ ДИАГНОСТИКА СИГНАЛОВ

## 🚀 Telegram команды (новые в v5.5)

```
/signal_stats       - Статистика сигналов (BUY/HOLD/SELL)
/signal_analysis    - Детальный анализ распределения голосов
```

---

## 📊 Что делать если нет BUY сигналов?

### 1. Проверь статистику:
```
/signal_stats
```

### 2. Проверь распределение:
```
/signal_analysis
```

### 3. Смотри на Max delta:
- **Если Max delta < 5** → рынок слабый, снизить `MIN_VOTES_FOR_BUY` до 3-4
- **Если Avg delta < 0** → рынок медвежий, стратегия правильно не покупает
- **Если Max delta ≥ 5, но BUY = 0** → проверь баланс и лимит позиций

---

## 📝 Логи для отправки мне

### Если нужна помощь, отправь:

**1. Вывод команд:**
```
/signal_stats
/signal_analysis
```

**2. Последние логи (Windows PowerShell):**
```powershell
Get-Content logs\bot.log -Tail 100 | Out-File diagnostic.txt
```

**3. Последние логи (Linux/Mac):**
```bash
tail -n 100 logs/bot.log > diagnostic.txt
```

**4. Фильтр только диагностики сигналов:**
```powershell
Get-Content logs\bot.log | Select-String "SIGNAL_DIAG" | Select-Object -Last 50 > signals.txt
```

---

## 🎯 Быстрые решения

| Проблема | Симптом | Решение |
|----------|---------|---------|
| **Нет BUY** | Max delta < 5 | `MIN_VOTES_FOR_BUY = 3` в config.py |
| **Нет BUY** | Avg delta < 0 | Рынок медвежий, подождать |
| **Блокировка** | "Лимит позиций" | Увеличить баланс или закрыть позиции |
| **Много SL** | SL слишком узкий | `DYNAMIC_SL_MIN = 0.020` (было 0.015) |
| **Маленькие позиции** | Size < 30% | Это нормально! Адаптивный sizing работает |

---

## 📈 Мониторинг в реальном времени

### Следи за логами:

**Windows PowerShell:**
```powershell
Get-Content logs\bot.log -Wait -Tail 20
```

**Linux/Mac:**
```bash
tail -f logs/bot.log
```

### Только важные события:
```powershell
Get-Content logs\bot.log -Wait | Select-String "OPEN_POSITION|CLOSE_POSITION|BUY СИГНАЛ"
```

---

## ✅ Чеклист перед запуском

- [ ] Бот запущен (`python bot.py`)
- [ ] Добавлены пары (`/add BTCUSDT`)
- [ ] Paper trading запущен (`/paper_start`)
- [ ] Проверена статистика через 10 минут (`/signal_stats`)
- [ ] Логи записываются в `logs/bot.log`

---

**Полное руководство:** `SIGNAL_DIAGNOSTICS_GUIDE.md`  
**Версия:** v5.5

