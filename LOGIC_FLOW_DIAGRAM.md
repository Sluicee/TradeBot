# Логика переключения режимов в Hybrid Strategy

## Проблема (ДО исправления)
```
ADX = 25.43 > 25 → должен быть TF режим
last_mode = TRANSITION, last_mode_time = 0.20h

1. Определение режима: current_mode = "TF" ✅
2. Защита от переключения:
   - last_mode != current_mode (TRANSITION != TF) ✅
   - last_mode_time < 1.0h (0.20h < 1.0h) ✅
   - БЛОКИРОВКА: current_mode = last_mode = "TRANSITION" ❌
```

## Решение (ПОСЛЕ исправления)
```
ADX = 25.43 > 25 → должен быть TF режим
last_mode = TRANSITION, last_mode_time = 0.20h

1. Определение режима: current_mode = "TF" ✅
2. Защита от переключения:
   - last_mode != current_mode (TRANSITION != TF) ✅
   - last_mode_time < 1.0h (0.20h < 1.0h) ✅
   - last_mode != "TRANSITION" (TRANSITION == TRANSITION) ❌
   - ИСКЛЮЧЕНИЕ: защита НЕ срабатывает ✅
3. Результат: current_mode = "TF" ✅
```

## Логика работы

### Определение режима по ADX
```
if adx < 15:
    current_mode = "MR" (Mean Reversion)
elif adx > 25:
    current_mode = "TF" (Trend Following)
else:
    current_mode = "TRANSITION" (15 ≤ ADX ≤ 25)
```

### Защита от частых переключений
```
if (last_mode != current_mode AND 
    last_mode_time < 1.0h AND 
    last_mode != "TRANSITION"):  # ← ИСКЛЮЧЕНИЕ
    # Блокировка переключения
    current_mode = last_mode
else:
    # Разрешить переключение
    current_mode = new_mode
```

### Исключения для TRANSITION режима
- TRANSITION → TF: разрешено немедленно (ADX > 25)
- TRANSITION → MR: разрешено немедленно (ADX < 15)
- MR ↔ TF: защищено 1 час
- TF ↔ MR: защищено 1 час

## Результат
- ✅ ADX > 25 → немедленный переход в TF режим
- ✅ ADX < 15 → немедленный переход в MR режим
- ✅ Защита от частых переключений MR ↔ TF сохранена
- ✅ SHORT сигналы будут генерироваться в TF режиме
