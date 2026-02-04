<p align="center">
  <a href="https://zenmoney.app"><img src="./docs/assets/logo.png" alt="Zenmoney logo"/></a>
</p>

This repository stores SMS and parsing formats and sender lists for banks.
It is designed to be easy to edit by non-developers and safe to validate.

---
- Formats and sender lists are maintained by the community.
- Each change is validated to prevent broken parsing.
- All data is stored in plain text.

---
[English](#english) | [Русский](#russian)

## English

### Repository structure

```
src/
  <bank name>_<bank id>/
    senders.txt
    formats/
      <format name>_<format id>.txt
```

- `bank name` and `format name` should be human-readable without `_` (use spaces).
  - Spaces in file/folder names are supported by Git and common OSes.
  - When using shell commands, quote paths with spaces.
- `bank id` and `format id` are numeric IDs from the database.
- If an ID is not known yet, it can be empty:
  - `bank name_` or `format name_`
  - `format name` without `_` is also treated as empty ID.

### Senders

`senders.txt` contains one sender per line.

- Empty lines are ignored.
- Lines starting with `#` are treated as senders, not comments.

### Format file

`formats/<format name>_<format id>.txt`

```
<regex>

-----COLUMNS-----
<col1>;<col2>;...;<colN>

-----EXAMPLE-----
<example 1>

-----EXAMPLE-----
<example 2>
```

- First line: regex in plain text.
- Add an empty line before each `-----COLUMNS-----` and `-----EXAMPLE-----` marker.
- `-----COLUMNS-----` is required and must be followed by a single `;`-separated line.
  - Columns are positional and correspond to regex capture groups.
  - If any column is empty, the format is informational (no transaction created).
- Each `-----EXAMPLE-----` section is required (at least one).
  - Examples can be multi-line until the next marker.
  - Examples are trimmed for validation/export.

### Column reference

Columns map regex groups to parsed fields. Use `field#arg` when a field needs an argument.
Columns are trimmed for validation/export.

| Column | Meaning | Notes |
| --- | --- | --- |
| `payee` | Merchant or counterparty name | |
| `income` | Income amount | Account currency |
| `outcome` | Outcome amount | Account currency |
| `fee` | Fee amount | Used to calculate net amount |
| `cashback` | Cashback amount | Used to calculate net amount |
| `op_income` | Income in original amount | Optional |
| `op_outcome` | Outcome in original amount | Optional |
| `balance` | Account balance | |
| `av_balance` | Available balance | |
| `comment` | Comment / extra text | |
| `instrument` / `op_instrument` | Original instrument symbol | Sets original instrument |
| `acc_instrument` | Account instrument symbol | Sets account instrument |
| `date#<format>` | Transaction date | Format string, e.g. `date#yyyy-MM-dd` |
| `syncid#<accountType>` | Account sync id | Optional transfer account type |
| `mcc` | Merchant category code | Integer |

### Contribution rules

- Keep changes focused: one bank/format per commit.
- Each file is committed separately with the provided scripts.
- Do not add comments to `senders.txt`.

### Validation rules (CI)

- Each format file must include regex, `COLUMNS`, and at least one `EXAMPLE`.
- Every example must match its own regex.
- Examples must not match regexes of other formats in the same bank.
- Group count in the match must equal the number of columns.
- Column names must be in the allowed list above.

## Russian

### Структура репозитория

```
src/
  <bank name>_<bank id>/
    senders.txt
    formats/
      <format name>_<format id>.txt
```

- `bank name` и `format name` — человекочитаемые и без `_` (используйте пробелы).
  - Пробелы в именах поддерживаются Git и обычными ОС.
  - В командах оболочки используйте кавычки для путей с пробелами.
- `bank id` и `format id` — числовые ID из базы.
- Если ID ещё неизвестен, он может быть пустым:
  - `bank name_` или `format name_`
  - `format name` без `_` также считается пустым ID.

### Отправители

`senders.txt` содержит одного отправителя на строку.

- Пустые строки игнорируются.
- Строки, начинающиеся с `#`, тоже считаются отправителями.

### Файл формата

`formats/<format name>_<format id>.txt`

```
<regex>

-----COLUMNS-----
<col1>;<col2>;...;<colN>

-----EXAMPLE-----
<example 1>

-----EXAMPLE-----
<example 2>
```

- Первая строка — regex.
- Перед каждым `-----COLUMNS-----` и `-----EXAMPLE-----` нужна пустая строка.
- `-----COLUMNS-----` обязателен и должен содержать одну строку с `;`.
  - Колонки позиционные и соответствуют группам regex.
  - Если есть пустая колонка, формат считается информационным.
- `-----EXAMPLE-----` обязателен (минимум один).
  - Пример может быть многострочным до следующего маркера.
  - Примеры триммятся при валидации/экспорте.

### Справочник колонок

Колонки сопоставляют группы regex с полями. Используйте `field#arg`, если нужен аргумент.
Колонки триммятся при валидации/экспорте.

| Колонка | Смысл | Примечание |
| --- | --- | --- |
| `payee` | Получатель / мерчант | |
| `income` | Сумма дохода | В валюте счёта |
| `outcome` | Сумма расхода | В валюте счёта |
| `fee` | Комиссия | Учитывается в итоговой сумме |
| `cashback` | Кешбэк | Учитывается в итоговой сумме |
| `op_income` | Доход в исходной сумме | Опционально |
| `op_outcome` | Расход в исходной сумме | Опционально |
| `balance` | Баланс счёта | |
| `av_balance` | Доступный баланс | |
| `comment` | Комментарий / доп. текст | |
| `instrument` / `op_instrument` | Символ исходной валюты | |
| `acc_instrument` | Символ валюты счёта | |
| `date#<format>` | Дата операции | Формат, напр. `date#yyyy-MM-dd` |
| `syncid#<accountType>` | Sync ID счёта | Тип для трансфера |
| `mcc` | MCC | Целое число |

### Правила участия

- Изменяйте одну сущность за раз.
- Каждый файл коммитится отдельно.
- Не используйте комментарии в `senders.txt`.

### Правила валидации (CI)

- В каждом формате обязателен regex, `COLUMNS` и минимум один `EXAMPLE`.
- Каждый пример обязан матчиться своим regex.
- Примеры не должны матчиться regex других форматов этого же банка.
- Количество групп должно совпадать с количеством колонок.
- Имена колонок должны быть из списка выше.

