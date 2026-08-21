# poh-backlog-skills, срез 1 — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Собрать решающий слой гигиены беклога: детерминированный аудит по правилам-данным, дифф между прогонами, план действий с ручным апрувом и память в `state/` плюс Backlog.md.

**Architecture:** Чистые функции над канонической моделью `BacklogItem`. Ноль сетевого I/O: вход — `items.json`, собранный host-агентом по `mappings/github.yaml`; выход — `findings.json`, `report.md`, `plan.md`, `plan.json`, снимок состояния. Правила описаны данными в `rules/catalog.yaml`, реализации регистрируются по `rule_id`. Правила-суждения в срезе 1 присутствуют в каталоге, но пропускаются движком.

**Tech Stack:** Python 3.11+, PyYAML, jsonschema, pytest, argparse (stdlib), Backlog.md CLI.

## Global Constraints

- Спека: `~/projects/poh-org/docs/superpowers/specs/2026-08-18-poh-backlog-skills-design.md`
- Корень репозитория: `~/projects/poh-org/poh-backlog-skills` (новый git-репозиторий, remote `po-helper-org/poh-backlog-skills`)
- Python ≥ 3.11. Зависимости рантайма только `PyYAML` и `jsonschema`; CLI на stdlib `argparse`
- Ноль сетевых вызовов в пакете `poh_backlog`. Никаких клиентов Jira/GitHub, никаких секретов в репозитории
- Никаких деструктивных операций: словарь операций плана содержит `propose_close`, `propose_merge`, `update_field`, `relink`, `split`, `comment`. Операции удаления нет
- Все идентификаторы правил стабильны и совпадают со спекой: `HYG-STALE-001`, `HYG-DESC-002`, `HYG-EST-003`, `HYG-ORPHAN-004`, `PHS-TAG-001`, `PHS-EPIC-002`, `PHS-MVP-003`, `PHS-LIMIT-004`, `PHS-GROW-005`, `PHS-SUP-006`, `PHS-SUP-007`, `PHS-DRIFT-008`
- Правила `kind: judgment` (`PHS-MVP-003`, `PHS-LIMIT-004`, `PHS-SUP-006`) в срезе 1 не исполняются: движок их пропускает и сообщает об этом
- Все новые правила заводятся с `maturity: experimental`
- Тексты в отчётах и планах — на русском, деловая проза без эмодзи
- Коммит после каждой задачи, тип по Conventional Commits

---

### Task 1: Каркас репозитория и каноническая модель

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/pyproject.toml`
- Create: `~/projects/poh-org/poh-backlog-skills/.gitignore`
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/__init__.py`
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/model.py`
- Create: `~/projects/poh-org/poh-backlog-skills/schemas/backlog-item.schema.json`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_model.py`

**Interfaces:**
- Consumes: ничего
- Produces: `BacklogItem` (frozen dataclass, поля `id: str`, `type: str`, `title: str`, `description: str`, `status: str`, `created_at: datetime`, `updated_at: datetime`, `labels: tuple[str, ...]`, `parent: str | None`, `estimate: float | None`, `extra: dict`), classmethod `BacklogItem.from_dict(raw: dict) -> BacklogItem`, property `phase_tags -> tuple[str, ...]`, property `is_open -> bool`, `Finding` (frozen dataclass, поля `rule_id: str`, `item_id: str`, `bucket: str`, `severity: str`, `message: str`, `evidence: dict`), `AuditContext` (dataclass, поля `items: dict[str, BacklogItem]`, `children: dict[str, list[str]]`, `profile`, `now: datetime`)

- [ ] **Step 1: Создать репозиторий и каталоги**

```bash
mkdir -p ~/projects/poh-org/poh-backlog-skills/{poh_backlog/rules,rules,schemas,mappings,tests/fixtures}
cd ~/projects/poh-org/poh-backlog-skills
git init
```

- [ ] **Step 2: Написать pyproject.toml и .gitignore**

`pyproject.toml`:

```toml
[project]
name = "poh-backlog-skills"
version = "0.1.0"
description = "Решающий слой гигиены беклога: правила, вердикты, план, память"
requires-python = ">=3.11"
dependencies = ["PyYAML>=6.0", "jsonschema>=4.0"]

[project.scripts]
poh-backlog = "poh_backlog.cli:main"

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-cov>=5.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["poh_backlog"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
__pycache__/
*.pyc
.venv/
.pytest_cache/
.coverage
runs/
```

- [ ] **Step 3: Написать падающий тест модели**

`tests/test_model.py`:

```python
from datetime import datetime, timezone

from poh_backlog.model import BacklogItem


RAW = {
    "id": "GH-412",
    "type": "story",
    "title": "Импорт CSV",
    "description": "Пользователь загружает файл",
    "status": "open",
    "created_at": "2026-01-10T10:00:00+00:00",
    "updated_at": "2026-03-01T12:30:00+00:00",
    "labels": ["mvp", "backend"],
    "parent": "GH-400",
    "estimate": 3.0,
    "extra": {"how_to_demo": None},
}


def test_from_dict_parses_all_fields():
    item = BacklogItem.from_dict(RAW)
    assert item.id == "GH-412"
    assert item.type == "story"
    assert item.labels == ("mvp", "backend")
    assert item.parent == "GH-400"
    assert item.estimate == 3.0
    assert item.created_at == datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc)
    assert item.updated_at == datetime(2026, 3, 1, 12, 30, tzinfo=timezone.utc)


def test_missing_optional_fields_default():
    item = BacklogItem.from_dict({
        "id": "GH-1",
        "type": "story",
        "title": "t",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    })
    assert item.description == ""
    assert item.labels == ()
    assert item.parent is None
    assert item.estimate is None
    assert item.extra == {}


def test_phase_tags_returns_only_phase_labels():
    item = BacklogItem.from_dict({**RAW, "labels": ["mvp", "grow", "backend"]})
    assert item.phase_tags == ("mvp", "grow")


def test_is_open():
    assert BacklogItem.from_dict(RAW).is_open is True
    assert BacklogItem.from_dict({**RAW, "status": "closed"}).is_open is False
```

- [ ] **Step 4: Запустить тест, убедиться что падает**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_model.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.model'`

- [ ] **Step 5: Реализовать модель**

`poh_backlog/__init__.py` — пустой файл.

`poh_backlog/model.py`:

```python
"""Каноническая модель элемента беклога и производные типы."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

PHASE_TAGS = ("mvp", "grow")


@dataclass(frozen=True)
class BacklogItem:
    id: str
    type: str
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    labels: tuple[str, ...]
    parent: str | None
    estimate: float | None
    extra: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BacklogItem":
        return cls(
            id=raw["id"],
            type=raw["type"],
            title=raw["title"],
            description=raw.get("description") or "",
            status=raw["status"],
            created_at=datetime.fromisoformat(raw["created_at"]),
            updated_at=datetime.fromisoformat(raw["updated_at"]),
            labels=tuple(raw.get("labels") or ()),
            parent=raw.get("parent"),
            estimate=raw.get("estimate"),
            extra=dict(raw.get("extra") or {}),
        )

    @property
    def phase_tags(self) -> tuple[str, ...]:
        return tuple(label for label in self.labels if label in PHASE_TAGS)

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    item_id: str
    bucket: str
    severity: str
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditContext:
    items: dict[str, BacklogItem]
    children: dict[str, list[str]]
    profile: Any
    now: datetime
```

- [ ] **Step 6: Написать JSON-схему элемента**

`schemas/backlog-item.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "BacklogItem",
  "type": "object",
  "required": ["id", "type", "title", "status", "created_at", "updated_at"],
  "properties": {
    "id": {"type": "string"},
    "type": {"enum": ["initiative", "epic", "story", "bug", "task"]},
    "title": {"type": "string"},
    "description": {"type": ["string", "null"]},
    "status": {"enum": ["open", "closed"]},
    "created_at": {"type": "string"},
    "updated_at": {"type": "string"},
    "labels": {"type": "array", "items": {"type": "string"}},
    "parent": {"type": ["string", "null"]},
    "estimate": {"type": ["number", "null"]},
    "extra": {"type": "object"}
  },
  "additionalProperties": false
}
```

- [ ] **Step 7: Запустить тест, убедиться что проходит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_model.py -v
```

Ожидается: 4 passed

- [ ] **Step 8: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: каноническая модель элемента беклога и каркас репозитория"
```

---

### Task 2: Профиль и пороги

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/rules/thresholds.yaml`
- Create: `~/projects/poh-org/poh-backlog-skills/backlog-profile.template.yaml`
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/profile.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_profile.py`

**Interfaces:**
- Consumes: ничего из предыдущих задач
- Produces: `Profile` (frozen dataclass, поле `values: dict`), метод `Profile.get(path: str) -> Any` с точечным путём вида `"staleness.story_days"`, функция `load_profile(defaults_path: Path, profile_path: Path | None = None) -> Profile`, исключение `ProfileError`

- [ ] **Step 1: Написать падающий тест**

`tests/test_profile.py`:

```python
from pathlib import Path

import pytest

from poh_backlog.profile import Profile, ProfileError, load_profile

DEFAULTS = Path(__file__).parent.parent / "rules" / "thresholds.yaml"


def test_defaults_load():
    profile = load_profile(DEFAULTS)
    assert profile.get("staleness.story_days") == 60
    assert profile.get("staleness.bug_days") == 30
    assert profile.get("description.min_words") == 20
    assert profile.get("phases.support_label") == "support"
    assert profile.get("plan.max_actions_per_run") == 50


def test_profile_overrides_defaults(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("staleness:\n  story_days: 90\n", encoding="utf-8")
    profile = load_profile(DEFAULTS, override)
    assert profile.get("staleness.story_days") == 90
    assert profile.get("staleness.bug_days") == 30


def test_unknown_key_raises(tmp_path):
    override = tmp_path / "backlog-profile.yaml"
    override.write_text("staleness:\n  story_weeks: 9\n", encoding="utf-8")
    with pytest.raises(ProfileError) as exc:
        load_profile(DEFAULTS, override)
    assert "staleness.story_weeks" in str(exc.value)


def test_missing_path_raises():
    profile = load_profile(DEFAULTS)
    with pytest.raises(ProfileError):
        profile.get("staleness.nope")
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_profile.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.profile'`

- [ ] **Step 3: Написать дефолты порогов**

`rules/thresholds.yaml`:

```yaml
# Дефолтные пороги. Переопределяются backlog-profile.yaml потребителя.
# Источники значений — раздел 3 спеки (опора на рынок).

staleness:
  # Порог отсутствия активности, после которого элемент считается протухшим.
  # Источник: backlog health benchmarks — менее 20% элементов старше 90 дней,
  # менее 5% старше 180. Для историй берём консервативные 60 дней.
  story_days: 60
  bug_days: 30

description:
  # Менее 20 слов означает минимальный контекст: замерено на 727 задачах,
  # ~40% выборки не проходят этот порог.
  min_words: 20

phases:
  mvp_tag: mvp
  grow_tag: grow
  # Метка, отличающая вечный Support-эпик от конечного эпика фичи.
  support_label: support
  # Обязательные атрибуты эпика фичи (PHS-EPIC-002).
  required_epic_fields: [business_metric, due_date, how_to_demo, limitations]

plan:
  # Явный потолок действий за прогон. Отложенное перечисляется в plan.md.
  max_actions_per_run: 50
```

- [ ] **Step 4: Написать шаблон профиля**

`backlog-profile.template.yaml`:

```yaml
# Доменный профиль. Скопировать в рабочее пространство как backlog-profile.yaml
# и переопределить только то, что отличается от дефолтов rules/thresholds.yaml.
# Неизвестный ключ — ошибка, а не молчание.

# staleness:
#   story_days: 90

# description:
#   min_words: 30

# phases:
#   support_label: support

# plan:
#   max_actions_per_run: 25

# Маппинг полей трекера. Используется host-агентом при сборе items.json.
mapping: mappings/github.yaml
```

- [ ] **Step 5: Реализовать загрузку профиля**

`poh_backlog/profile.py`:

```python
"""Загрузка и слияние порогов: дефолты, затем доменный профиль."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ProfileError(Exception):
    """Битый профиль, неизвестный ключ или обращение к несуществующему пути."""


@dataclass(frozen=True)
class Profile:
    values: dict[str, Any]

    def get(self, path: str) -> Any:
        node: Any = self.values
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                raise ProfileError(f"Порог не найден: {path}")
            node = node[part]
        return node


def _merge(defaults: dict, override: dict, prefix: str = "") -> dict:
    merged = dict(defaults)
    for key, value in override.items():
        path = f"{prefix}{key}"
        if key not in defaults:
            raise ProfileError(f"Неизвестный ключ профиля: {path}")
        if isinstance(defaults[key], dict) and isinstance(value, dict):
            merged[key] = _merge(defaults[key], value, prefix=f"{path}.")
        else:
            merged[key] = value
    return merged


def load_profile(defaults_path: Path, profile_path: Path | None = None) -> Profile:
    defaults = yaml.safe_load(Path(defaults_path).read_text(encoding="utf-8")) or {}
    if profile_path is None:
        return Profile(defaults)
    raw = yaml.safe_load(Path(profile_path).read_text(encoding="utf-8")) or {}
    override = {k: v for k, v in raw.items() if k != "mapping"}
    return Profile(_merge(defaults, override))
```

- [ ] **Step 6: Запустить тест, убедиться что проходит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_profile.py -v
```

Ожидается: 4 passed

- [ ] **Step 7: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: профиль и разрешение порогов с валидацией ключей"
```

---

### Task 3: Каталог правил

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/rules/catalog.yaml`
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/catalog.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_catalog.py`

**Interfaces:**
- Consumes: ничего
- Produces: `RuleSpec` (frozen dataclass, поля `id: str`, `title: str`, `bucket: str`, `kind: str`, `severity: str`, `threshold: str | None`, `action: str`, `maturity: str`, `expected_effect: str | None`), функция `load_catalog(path: Path) -> dict[str, RuleSpec]`, константы `BUCKETS: tuple[str, ...]`, `KINDS: tuple[str, ...]`, `MATURITIES: tuple[str, ...]`, исключение `CatalogError`

- [ ] **Step 1: Написать падающий тест**

`tests/test_catalog.py`:

```python
from pathlib import Path

import pytest

from poh_backlog.catalog import BUCKETS, CatalogError, load_catalog

CATALOG = Path(__file__).parent.parent / "rules" / "catalog.yaml"

EXPECTED_IDS = {
    "HYG-STALE-001", "HYG-DESC-002", "HYG-EST-003", "HYG-ORPHAN-004",
    "PHS-TAG-001", "PHS-EPIC-002", "PHS-MVP-003", "PHS-LIMIT-004",
    "PHS-GROW-005", "PHS-SUP-006", "PHS-SUP-007", "PHS-DRIFT-008",
}


def test_catalog_contains_all_spec_rules():
    catalog = load_catalog(CATALOG)
    assert set(catalog) == EXPECTED_IDS


def test_every_rule_has_valid_bucket_and_starts_experimental():
    catalog = load_catalog(CATALOG)
    for spec in catalog.values():
        assert spec.bucket in BUCKETS, spec.id
        assert spec.maturity == "experimental", spec.id


def test_judgment_rules_marked():
    catalog = load_catalog(CATALOG)
    judgment = {rid for rid, spec in catalog.items() if spec.kind == "judgment"}
    assert judgment == {"PHS-MVP-003", "PHS-LIMIT-004", "PHS-SUP-006"}


def test_invalid_bucket_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    bad.write_text(
        "- id: X-1\n  title: t\n  bucket: nuke\n  kind: deterministic\n"
        "  severity: low\n  action: comment\n  maturity: experimental\n",
        encoding="utf-8",
    )
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_duplicate_id_raises(tmp_path):
    bad = tmp_path / "catalog.yaml"
    entry = ("- id: X-1\n  title: t\n  bucket: update\n  kind: deterministic\n"
             "  severity: low\n  action: comment\n  maturity: experimental\n")
    bad.write_text(entry * 2, encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(bad)
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_catalog.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.catalog'`

- [ ] **Step 3: Написать каталог правил**

`rules/catalog.yaml`:

```yaml
# Каталог правил гигиены беклога. Данные, не код.
# rule_id стабилен и сквозной: finding -> план -> комментарий трекера -> снимок.

- id: HYG-STALE-001
  title: Элемент без активности дольше порога
  bucket: close
  kind: deterministic
  severity: medium
  threshold: staleness.story_days
  action: propose_close
  expected_effect: "item has label 'stale' and comment with rule_id"
  maturity: experimental
  rationale: Возраст без активности и без связанной работы означает кандидата на закрытие
  source: "backlog health: менее 20% элементов старше 90 дней, менее 5% старше 180"

- id: HYG-DESC-002
  title: Описание короче порога
  bucket: update
  kind: deterministic
  severity: medium
  threshold: description.min_words
  action: update_field
  expected_effect: "item description word count >= threshold"
  maturity: experimental
  rationale: Минимальный контекст делает задачу неоценимой и неисполнимой
  source: "замер 727 задач: ~40% короче 20 слов, ~27% без описания вовсе"

- id: HYG-EST-003
  title: История без оценки
  bucket: update
  kind: deterministic
  severity: low
  threshold: null
  action: update_field
  expected_effect: "item estimate is not null"
  maturity: experimental
  rationale: Элемент без оценки не проходит Definition of Ready
  source: "DEEP: estimated"

- id: HYG-ORPHAN-004
  title: История без родителя
  bucket: link
  kind: deterministic
  severity: medium
  threshold: null
  action: relink
  expected_effect: "item parent is not null"
  maturity: experimental
  rationale: Сирота не видна в иерархии и выпадает из планирования
  source: "Advanced Roadmaps: отчёт orphan issues"

- id: PHS-TAG-001
  title: История в эпике фичи без ровно одного тега фазы
  bucket: update
  kind: deterministic
  severity: high
  threshold: null
  action: update_field
  expected_effect: "item has exactly one of mvp/grow labels"
  maturity: experimental
  rationale: Без тега невозможно отличить сутевую часть от Grow-хвоста
  source: "раздел 5 спеки"

- id: PHS-EPIC-002
  title: Эпик фичи без обязательных атрибутов
  bucket: update
  kind: deterministic
  severity: high
  threshold: phases.required_epic_fields
  action: update_field
  expected_effect: "epic has business_metric, due_date, how_to_demo, limitations"
  maturity: experimental
  rationale: Без бизнес-метрики, срока, HowToDemo и списка ограничений эпик не готов к старту
  source: "раздел 5 спеки"

- id: PHS-MVP-003
  title: MVP-история не нужна для прохождения HowToDemo
  bucket: update
  kind: judgment
  severity: high
  threshold: null
  action: update_field
  expected_effect: "item label mvp replaced by grow"
  maturity: experimental
  prompt: prompts/mvp_necessity.md
  rationale: HowToDemo делает принадлежность к MVP проверяемой, а не вкусовой
  source: "раздел 5.1 спеки"

- id: PHS-LIMIT-004
  title: Ограничение MVP без Grow-истории и без явного принятия
  bucket: split
  kind: judgment
  severity: high
  threshold: null
  action: split
  expected_effect: "limitation has linked grow story or accepted marker"
  maturity: experimental
  prompt: prompts/limitation_coverage.md
  rationale: Необращённое ограничение — техдолг, которого нет ни в одном списке
  source: "раздел 5.1 спеки"

- id: PHS-GROW-005
  title: Эпик фичи закрыт при открытых Grow-историях
  bucket: update
  kind: deterministic
  severity: high
  threshold: null
  action: update_field
  expected_effect: "epic reopened or grow children moved"
  maturity: experimental
  rationale: Закрытие эпика с открытым хвостом прячет незавершённую работу
  source: "раздел 5.1 спеки"

- id: PHS-SUP-006
  title: Задача поддержки живёт в эпике фичи
  bucket: link
  kind: judgment
  severity: medium
  threshold: null
  action: relink
  expected_effect: "item parent is the support epic of the initiative"
  maturity: experimental
  prompt: prompts/support_leak.md
  rationale: Утечка Support раздувает конечный эпик и ломает его сроки
  source: "раздел 5.1 спеки"

- id: PHS-SUP-007
  title: У инициативы не ровно один Support-эпик
  bucket: link
  kind: deterministic
  severity: high
  threshold: phases.support_label
  action: relink
  expected_effect: "initiative has exactly one open support epic"
  maturity: experimental
  rationale: Support-эпик один на бизнес-инициативу и не закрывается
  source: "раздел 5.1 спеки"

- id: PHS-DRIFT-008
  title: Перевод истории grow в mvp без обоснования
  bucket: update
  kind: deterministic
  severity: high
  threshold: null
  action: comment
  expected_effect: "item has comment explaining phase change"
  maturity: experimental
  rationale: Тег переставляется незаметно, дрейф виден только на диффе снимков
  source: "раздел 5 спеки"
```

- [ ] **Step 4: Создать промпты, на которые ссылается каталог**

Правила-суждения в срезе 1 не исполняются, но каталог на них ссылается —
висячих ссылок быть не должно.

`prompts/mvp_necessity.md`:

```markdown
# PHS-MVP-003 — нужна ли история для HowToDemo

Дано: текст HowToDemo эпика фичи и одна история с тегом `mvp`.

Вопрос: пройдёт ли HowToDemo целиком, если этой истории не будет?

Ответ строго в JSON:
{"necessary": true|false, "confidence": 0.0-1.0, "reason": "одно предложение"}

Правила: при сомнении отвечай `necessary: true`. Ложный перевод нужной истории
в grow ломает демо, обратная ошибка лишь оставляет лишнюю историю в MVP.
```

`prompts/limitation_coverage.md`:

```markdown
# PHS-LIMIT-004 — обращено ли ограничение MVP в работу

Дано: одно ограничение из списка ограничений эпика фичи и заголовки всех историй
с тегом `grow` в этом эпике.

Вопрос: покрыто ли ограничение какой-либо из этих историй?

Ответ строго в JSON:
{"covered": true|false, "story_id": "ID или null", "confidence": 0.0-1.0,
 "reason": "одно предложение"}

Правила: частичное покрытие считается непокрытым. Необращённое ограничение —
техдолг, которого нет ни в одном списке.
```

`prompts/support_leak.md`:

```markdown
# PHS-SUP-006 — является ли задача поддержкой

Дано: задача из эпика фичи, дата прод-релиза фичи и текст задачи.

Вопрос: это работа по поддержке уже выпущенного (баг, запрос, мелкое улучшение)
или часть исходного объёма фичи?

Ответ строго в JSON:
{"is_support": true|false, "confidence": 0.0-1.0, "reason": "одно предложение"}

Правила: задача, созданная до прод-релиза, поддержкой не является.
```

- [ ] **Step 5: Реализовать загрузку каталога**

`poh_backlog/catalog.py`:

```python
"""Каталог правил: чтение YAML-данных и валидация."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

BUCKETS = ("close", "merge", "update", "split", "link", "no-action")
KINDS = ("deterministic", "judgment")
MATURITIES = ("experimental", "advisory", "trusted")


class CatalogError(Exception):
    """Битая запись каталога."""


@dataclass(frozen=True)
class RuleSpec:
    id: str
    title: str
    bucket: str
    kind: str
    severity: str
    threshold: str | None
    action: str
    maturity: str
    expected_effect: str | None


def _spec(entry: dict[str, Any]) -> RuleSpec:
    try:
        spec = RuleSpec(
            id=entry["id"],
            title=entry["title"],
            bucket=entry["bucket"],
            kind=entry["kind"],
            severity=entry["severity"],
            threshold=entry.get("threshold"),
            action=entry["action"],
            maturity=entry["maturity"],
            expected_effect=entry.get("expected_effect"),
        )
    except KeyError as exc:
        raise CatalogError(f"В записи каталога нет обязательного поля: {exc}") from exc
    if spec.bucket not in BUCKETS:
        raise CatalogError(f"{spec.id}: недопустимая корзина {spec.bucket}")
    if spec.kind not in KINDS:
        raise CatalogError(f"{spec.id}: недопустимый вид {spec.kind}")
    if spec.maturity not in MATURITIES:
        raise CatalogError(f"{spec.id}: недопустимая зрелость {spec.maturity}")
    return spec


def load_catalog(path: Path) -> dict[str, RuleSpec]:
    entries = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or []
    catalog: dict[str, RuleSpec] = {}
    for entry in entries:
        spec = _spec(entry)
        if spec.id in catalog:
            raise CatalogError(f"Дублирующийся идентификатор правила: {spec.id}")
        catalog[spec.id] = spec
    return catalog
```

- [ ] **Step 6: Запустить тест, убедиться что проходит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_catalog.py -v
```

Ожидается: 5 passed

- [ ] **Step 7: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: каталог правил как данные с валидацией"
```

---

### Task 4: Реестр правил и сборка контекста

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/rules/__init__.py`
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/context.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_context.py`

**Interfaces:**
- Consumes: `BacklogItem`, `AuditContext`, `Finding` из `poh_backlog.model`; `Profile` из `poh_backlog.profile`
- Produces: `RULES: dict[str, RuleFn]` где `RuleFn = Callable[[BacklogItem, AuditContext], list[Finding]]`, декоратор `rule(rule_id: str)`, функция `build_context(items: list[BacklogItem], profile: Profile, now: datetime) -> AuditContext`, хелперы `is_feature_epic(item, profile) -> bool`, `is_support_epic(item, profile) -> bool`

- [ ] **Step 1: Написать падающий тест**

`tests/test_context.py`:

```python
from datetime import datetime, timezone

from poh_backlog.context import build_context, is_feature_epic, is_support_epic
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({"phases": {"support_label": "support"}})


def item(id_, type_="story", parent=None, labels=()):
    return BacklogItem.from_dict({
        "id": id_, "type": type_, "title": id_, "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "parent": parent, "labels": list(labels),
    })


def test_build_context_indexes_items_and_children():
    items = [item("I-1", "initiative"), item("E-1", "epic", parent="I-1"),
             item("S-1", parent="E-1"), item("S-2", parent="E-1")]
    ctx = build_context(items, PROFILE, NOW)
    assert set(ctx.items) == {"I-1", "E-1", "S-1", "S-2"}
    assert ctx.children["E-1"] == ["S-1", "S-2"]
    assert ctx.children["I-1"] == ["E-1"]
    assert ctx.children["S-1"] == []
    assert ctx.now == NOW


def test_feature_epic_versus_support_epic():
    feature = item("E-1", "epic")
    support = item("E-2", "epic", labels=("support",))
    story = item("S-1")
    assert is_feature_epic(feature, PROFILE) is True
    assert is_feature_epic(support, PROFILE) is False
    assert is_feature_epic(story, PROFILE) is False
    assert is_support_epic(support, PROFILE) is True
    assert is_support_epic(feature, PROFILE) is False
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_context.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.context'`

- [ ] **Step 3: Реализовать контекст и хелперы**

`poh_backlog/context.py`:

```python
"""Сборка контекста аудита и предикаты типов элементов."""
from __future__ import annotations

from datetime import datetime

from poh_backlog.model import AuditContext, BacklogItem
from poh_backlog.profile import Profile


def build_context(items: list[BacklogItem], profile: Profile, now: datetime) -> AuditContext:
    by_id = {item.id: item for item in items}
    children: dict[str, list[str]] = {item.id: [] for item in items}
    for item in items:
        if item.parent and item.parent in children:
            children[item.parent].append(item.id)
    return AuditContext(items=by_id, children=children, profile=profile, now=now)


def is_support_epic(item: BacklogItem, profile: Profile) -> bool:
    return item.type == "epic" and profile.get("phases.support_label") in item.labels


def is_feature_epic(item: BacklogItem, profile: Profile) -> bool:
    return item.type == "epic" and not is_support_epic(item, profile)
```

- [ ] **Step 4: Реализовать реестр правил**

`poh_backlog/rules/__init__.py`:

```python
"""Реестр реализаций правил: rule_id -> функция."""
from __future__ import annotations

from typing import Callable

from poh_backlog.model import AuditContext, BacklogItem, Finding

RuleFn = Callable[[BacklogItem, AuditContext], list[Finding]]

RULES: dict[str, RuleFn] = {}


def rule(rule_id: str) -> Callable[[RuleFn], RuleFn]:
    def decorator(fn: RuleFn) -> RuleFn:
        if rule_id in RULES:
            raise RuntimeError(f"Правило уже зарегистрировано: {rule_id}")
        RULES[rule_id] = fn
        return fn

    return decorator
```

- [ ] **Step 5: Запустить тест, убедиться что проходит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_context.py -v
```

Ожидается: 2 passed

- [ ] **Step 6: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: реестр правил и сборка контекста аудита"
```

---

### Task 5: Детерминированные правила гигиены

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/rules/hygiene.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_rules_hygiene.py`

**Interfaces:**
- Consumes: `rule` и `RULES` из `poh_backlog.rules`; `BacklogItem`, `AuditContext`, `Finding` из `poh_backlog.model`
- Produces: регистрации `HYG-STALE-001`, `HYG-DESC-002`, `HYG-EST-003`, `HYG-ORPHAN-004` в `RULES`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_rules_hygiene.py`:

```python
from datetime import datetime, timedelta, timezone

import poh_backlog.rules.hygiene  # noqa: F401  регистрация правил
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({
    "staleness": {"story_days": 60, "bug_days": 30},
    "description": {"min_words": 20},
    "phases": {"support_label": "support"},
})
LONG_TEXT = " ".join(["слово"] * 25)


def item(id_, **over):
    raw = {
        "id": id_, "type": "story", "title": id_, "status": "open",
        "description": LONG_TEXT,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": (NOW - timedelta(days=1)).isoformat(),
        "parent": "E-1", "estimate": 3.0, "labels": ["mvp"],
    }
    raw.update(over)
    return BacklogItem.from_dict(raw)


def ctx(items):
    return build_context(items, PROFILE, NOW)


def test_stale_story_flagged_after_threshold():
    old = item("S-1", updated_at=(NOW - timedelta(days=61)).isoformat())
    findings = RULES["HYG-STALE-001"](old, ctx([old]))
    assert len(findings) == 1
    assert findings[0].bucket == "close"
    assert findings[0].evidence["days_since_update"] == 61


def test_stale_bug_uses_bug_threshold():
    bug = item("B-1", type="bug", updated_at=(NOW - timedelta(days=31)).isoformat())
    assert RULES["HYG-STALE-001"](bug, ctx([bug]))


def test_fresh_and_closed_items_not_flagged():
    fresh = item("S-2")
    closed = item("S-3", status="closed",
                  updated_at=(NOW - timedelta(days=400)).isoformat())
    assert RULES["HYG-STALE-001"](fresh, ctx([fresh])) == []
    assert RULES["HYG-STALE-001"](closed, ctx([closed])) == []


def test_short_description_flagged():
    short = item("S-4", description="слишком коротко")
    findings = RULES["HYG-DESC-002"](short, ctx([short]))
    assert len(findings) == 1
    assert findings[0].bucket == "update"
    assert findings[0].evidence["word_count"] == 2


def test_long_description_not_flagged():
    assert RULES["HYG-DESC-002"](item("S-5"), ctx([item("S-5")])) == []


def test_missing_estimate_flagged_only_for_open_story():
    no_est = item("S-6", estimate=None)
    epic = item("E-9", type="epic", estimate=None)
    assert len(RULES["HYG-EST-003"](no_est, ctx([no_est]))) == 1
    assert RULES["HYG-EST-003"](epic, ctx([epic])) == []


def test_orphan_story_flagged():
    orphan = item("S-7", parent=None)
    findings = RULES["HYG-ORPHAN-004"](orphan, ctx([orphan]))
    assert len(findings) == 1
    assert findings[0].bucket == "link"


def test_initiative_without_parent_not_orphan():
    top = item("I-1", type="initiative", parent=None)
    assert RULES["HYG-ORPHAN-004"](top, ctx([top])) == []
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_rules_hygiene.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.rules.hygiene'`

- [ ] **Step 3: Реализовать правила**

`poh_backlog/rules/hygiene.py`:

```python
"""Детерминированные правила гигиены: HYG-*."""
from __future__ import annotations

from poh_backlog.model import AuditContext, BacklogItem, Finding
from poh_backlog.rules import rule

ESTIMATED_TYPES = ("story", "bug", "task")
PARENTED_TYPES = ("story", "bug", "task")


@rule("HYG-STALE-001")
def stale(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open:
        return []
    key = "staleness.bug_days" if item.type == "bug" else "staleness.story_days"
    limit = ctx.profile.get(key)
    days = (ctx.now - item.updated_at).days
    if days < limit:
        return []
    return [Finding(
        rule_id="HYG-STALE-001",
        item_id=item.id,
        bucket="close",
        severity="medium",
        message=f"Нет активности {days} дней при пороге {limit}",
        evidence={"days_since_update": days, "threshold_days": limit},
    )]


@rule("HYG-DESC-002")
def short_description(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open:
        return []
    limit = ctx.profile.get("description.min_words")
    words = len(item.description.split())
    if words >= limit:
        return []
    return [Finding(
        rule_id="HYG-DESC-002",
        item_id=item.id,
        bucket="update",
        severity="medium",
        message=f"Описание из {words} слов при пороге {limit}",
        evidence={"word_count": words, "threshold_words": limit},
    )]


@rule("HYG-EST-003")
def missing_estimate(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in ESTIMATED_TYPES:
        return []
    if item.estimate is not None:
        return []
    return [Finding(
        rule_id="HYG-EST-003",
        item_id=item.id,
        bucket="update",
        severity="low",
        message="Нет оценки: элемент не проходит Definition of Ready",
        evidence={},
    )]


@rule("HYG-ORPHAN-004")
def orphan(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in PARENTED_TYPES:
        return []
    if item.parent is not None:
        return []
    return [Finding(
        rule_id="HYG-ORPHAN-004",
        item_id=item.id,
        bucket="link",
        severity="medium",
        message="Нет родителя: элемент выпадает из иерархии и планирования",
        evidence={},
    )]
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_rules_hygiene.py -v
```

Ожидается: 8 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: детерминированные правила гигиены HYG-*"
```

---

### Task 6: Правила фаз по снимку

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/rules/phases.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_rules_phases.py`

**Interfaces:**
- Consumes: `rule` из `poh_backlog.rules`; `is_feature_epic`, `is_support_epic` из `poh_backlog.context`
- Produces: регистрации `PHS-TAG-001`, `PHS-EPIC-002`, `PHS-GROW-005`, `PHS-SUP-007` в `RULES`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_rules_phases.py`:

```python
from datetime import datetime, timezone

import poh_backlog.rules.phases  # noqa: F401  регистрация правил
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES

NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
PROFILE = Profile({"phases": {
    "mvp_tag": "mvp", "grow_tag": "grow", "support_label": "support",
    "required_epic_fields": ["business_metric", "due_date", "how_to_demo", "limitations"],
}})
FULL_EPIC_EXTRA = {
    "business_metric": "конверсия импорта +10%",
    "due_date": "2026-10-01",
    "how_to_demo": "Загрузить CSV на 100 строк и увидеть таблицу",
    "limitations": ["без валидации кодировок", "только UTF-8"],
}


def item(id_, type_="story", status="open", parent=None, labels=(), extra=None):
    return BacklogItem.from_dict({
        "id": id_, "type": type_, "title": id_, "status": status,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
        "parent": parent, "labels": list(labels), "extra": extra or {},
    })


def ctx(items):
    return build_context(items, PROFILE, NOW)


def test_story_in_feature_epic_without_phase_tag_flagged():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1")
    findings = RULES["PHS-TAG-001"](story, ctx([epic, story]))
    assert len(findings) == 1
    assert findings[0].evidence["phase_tags"] == []


def test_story_with_both_tags_flagged():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1", labels=("mvp", "grow"))
    findings = RULES["PHS-TAG-001"](story, ctx([epic, story]))
    assert len(findings) == 1
    assert findings[0].evidence["phase_tags"] == ["mvp", "grow"]


def test_story_with_one_tag_clean():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    story = item("S-1", parent="E-1", labels=("mvp",))
    assert RULES["PHS-TAG-001"](story, ctx([epic, story])) == []


def test_story_in_support_epic_not_required_to_have_phase_tag():
    support = item("E-2", "epic", labels=("support",))
    story = item("S-2", parent="E-2")
    assert RULES["PHS-TAG-001"](story, ctx([support, story])) == []


def test_feature_epic_missing_fields_flagged():
    epic = item("E-1", "epic", extra={"business_metric": "x"})
    findings = RULES["PHS-EPIC-002"](epic, ctx([epic]))
    assert len(findings) == 1
    assert findings[0].evidence["missing"] == ["due_date", "how_to_demo", "limitations"]


def test_complete_feature_epic_clean():
    epic = item("E-1", "epic", extra=FULL_EPIC_EXTRA)
    assert RULES["PHS-EPIC-002"](epic, ctx([epic])) == []


def test_support_epic_exempt_from_required_fields():
    support = item("E-2", "epic", labels=("support",))
    assert RULES["PHS-EPIC-002"](support, ctx([support])) == []


def test_closed_epic_with_open_grow_children_flagged():
    epic = item("E-1", "epic", status="closed", extra=FULL_EPIC_EXTRA)
    grow = item("S-1", parent="E-1", labels=("grow",))
    findings = RULES["PHS-GROW-005"](epic, ctx([epic, grow]))
    assert len(findings) == 1
    assert findings[0].evidence["open_grow"] == ["S-1"]


def test_closed_epic_without_open_grow_clean():
    epic = item("E-1", "epic", status="closed", extra=FULL_EPIC_EXTRA)
    done = item("S-1", parent="E-1", status="closed", labels=("grow",))
    assert RULES["PHS-GROW-005"](epic, ctx([epic, done])) == []


def test_initiative_without_support_epic_flagged():
    initiative = item("I-1", "initiative")
    feature = item("E-1", "epic", parent="I-1", extra=FULL_EPIC_EXTRA)
    findings = RULES["PHS-SUP-007"](initiative, ctx([initiative, feature]))
    assert len(findings) == 1
    assert findings[0].evidence["support_epics"] == []


def test_initiative_with_two_support_epics_flagged():
    initiative = item("I-1", "initiative")
    s1 = item("E-1", "epic", parent="I-1", labels=("support",))
    s2 = item("E-2", "epic", parent="I-1", labels=("support",))
    findings = RULES["PHS-SUP-007"](initiative, ctx([initiative, s1, s2]))
    assert findings[0].evidence["support_epics"] == ["E-1", "E-2"]


def test_initiative_with_exactly_one_support_epic_clean():
    initiative = item("I-1", "initiative")
    support = item("E-1", "epic", parent="I-1", labels=("support",))
    assert RULES["PHS-SUP-007"](initiative, ctx([initiative, support])) == []
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_rules_phases.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.rules.phases'`

- [ ] **Step 3: Реализовать правила фаз**

`poh_backlog/rules/phases.py`:

```python
"""Инварианты модели фаз по одному снимку: PHS-* кроме дрейфа."""
from __future__ import annotations

from poh_backlog.context import is_feature_epic, is_support_epic
from poh_backlog.model import AuditContext, BacklogItem, Finding
from poh_backlog.rules import rule

PHASED_TYPES = ("story", "bug", "task")


@rule("PHS-TAG-001")
def exactly_one_phase_tag(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not item.is_open or item.type not in PHASED_TYPES or item.parent is None:
        return []
    parent = ctx.items.get(item.parent)
    if parent is None or not is_feature_epic(parent, ctx.profile):
        return []
    tags = list(item.phase_tags)
    if len(tags) == 1:
        return []
    return [Finding(
        rule_id="PHS-TAG-001",
        item_id=item.id,
        bucket="update",
        severity="high",
        message=f"Тегов фазы {len(tags)} вместо одного: {tags or 'нет ни одного'}",
        evidence={"phase_tags": tags, "epic": parent.id},
    )]


@rule("PHS-EPIC-002")
def feature_epic_required_fields(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if not is_feature_epic(item, ctx.profile):
        return []
    required = ctx.profile.get("phases.required_epic_fields")
    missing = [name for name in required if not item.extra.get(name)]
    if not missing:
        return []
    return [Finding(
        rule_id="PHS-EPIC-002",
        item_id=item.id,
        bucket="update",
        severity="high",
        message="Эпик фичи не готов к старту, нет атрибутов: " + ", ".join(missing),
        evidence={"missing": missing},
    )]


@rule("PHS-GROW-005")
def closed_epic_with_open_grow(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if item.is_open or not is_feature_epic(item, ctx.profile):
        return []
    grow_tag = ctx.profile.get("phases.grow_tag")
    open_grow = [
        child_id for child_id in ctx.children.get(item.id, [])
        if ctx.items[child_id].is_open and grow_tag in ctx.items[child_id].labels
    ]
    if not open_grow:
        return []
    return [Finding(
        rule_id="PHS-GROW-005",
        item_id=item.id,
        bucket="update",
        severity="high",
        message=f"Эпик закрыт при {len(open_grow)} открытых Grow-историях",
        evidence={"open_grow": open_grow},
    )]


@rule("PHS-SUP-007")
def one_support_epic_per_initiative(item: BacklogItem, ctx: AuditContext) -> list[Finding]:
    if item.type != "initiative" or not item.is_open:
        return []
    support = [
        child_id for child_id in ctx.children.get(item.id, [])
        if is_support_epic(ctx.items[child_id], ctx.profile)
    ]
    if len(support) == 1:
        return []
    return [Finding(
        rule_id="PHS-SUP-007",
        item_id=item.id,
        bucket="link",
        severity="high",
        message=f"Support-эпиков у инициативы {len(support)}, должен быть ровно один",
        evidence={"support_epics": support},
    )]
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_rules_phases.py -v
```

Ожидается: 12 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: инварианты модели фаз PHS-* по снимку"
```

---

### Task 7: Подавления из decisions.yaml

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/suppress.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_suppress.py`

**Interfaces:**
- Consumes: `Finding` из `poh_backlog.model`
- Produces: `Suppression` (frozen dataclass, поля `rule_id: str`, `item_id: str`, `until: date | None`), `load_suppressions(path: Path) -> list[Suppression]`, `is_suppressed(finding: Finding, suppressions: list[Suppression], today: date) -> bool`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_suppress.py`:

```python
from datetime import date

from poh_backlog.model import Finding
from poh_backlog.suppress import is_suppressed, load_suppressions

TODAY = date(2026, 8, 18)


def finding(rule_id="HYG-STALE-001", item_id="GH-412"):
    return Finding(rule_id=rule_id, item_id=item_id, bucket="close",
                   severity="medium", message="m", evidence={})


def write(tmp_path, text):
    path = tmp_path / "decisions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_file_gives_empty_list(tmp_path):
    assert load_suppressions(tmp_path / "nope.yaml") == []


def test_forever_suppression_blocks(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: живая\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is True


def test_dated_suppression_expires(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: rejected\n  reason: ждём релиз\n  suppress_until: 2026-08-01\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is False
    assert is_suppressed(finding(), sup, date(2026, 7, 1)) is True


def test_accepted_verdict_does_not_suppress(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-412\n"
                 "  verdict: accepted\n  reason: ок\n  suppress_until: forever\n")
    assert load_suppressions(path) == []


def test_other_item_not_suppressed(tmp_path):
    path = write(tmp_path,
                 "- rule_id: HYG-STALE-001\n  item: GH-999\n"
                 "  verdict: rejected\n  reason: r\n  suppress_until: forever\n")
    sup = load_suppressions(path)
    assert is_suppressed(finding(), sup, TODAY) is False
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_suppress.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.suppress'`

- [ ] **Step 3: Реализовать подавления**

`poh_backlog/suppress.py`:

```python
"""Подавления: отклонённое человеком не возвращается каждый прогон."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from poh_backlog.model import Finding


@dataclass(frozen=True)
class Suppression:
    rule_id: str
    item_id: str
    until: date | None  # None означает forever


def load_suppressions(path: Path) -> list[Suppression]:
    path = Path(path)
    if not path.exists():
        return []
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    result: list[Suppression] = []
    for entry in entries:
        if entry.get("verdict") != "rejected":
            continue
        raw_until = entry.get("suppress_until", "forever")
        until = None if raw_until in (None, "forever") else _as_date(raw_until)
        result.append(Suppression(entry["rule_id"], entry["item"], until))
    return result


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def is_suppressed(finding: Finding, suppressions: list[Suppression], today: date) -> bool:
    for sup in suppressions:
        if sup.rule_id != finding.rule_id or sup.item_id != finding.item_id:
            continue
        if sup.until is None or today < sup.until:
            return True
    return False
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_suppress.py -v
```

Ожидается: 5 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: подавления findings из decisions.yaml"
```

---

### Task 8: Движок аудита

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/audit.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_audit.py`

**Interfaces:**
- Consumes: `RULES` из `poh_backlog.rules`, `build_context` из `poh_backlog.context`, `load_catalog`/`RuleSpec` из `poh_backlog.catalog`, `is_suppressed` из `poh_backlog.suppress`
- Produces: `AuditResult` (frozen dataclass, поля `findings: list[Finding]`, `skipped_rules: list[str]`, `suppressed: int`), функция `run_audit(items: list[BacklogItem], catalog: dict[str, RuleSpec], profile: Profile, now: datetime, suppressions: list[Suppression]) -> AuditResult`, функция `findings_to_dicts(findings: list[Finding]) -> list[dict]`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_audit.py`:

```python
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import poh_backlog.rules.hygiene  # noqa: F401
import poh_backlog.rules.phases  # noqa: F401
from poh_backlog.audit import findings_to_dicts, run_audit
from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem
from poh_backlog.profile import load_profile
from poh_backlog.suppress import Suppression

ROOT = Path(__file__).parent.parent
NOW = datetime(2026, 8, 18, tzinfo=timezone.utc)
CATALOG = load_catalog(ROOT / "rules" / "catalog.yaml")
PROFILE = load_profile(ROOT / "rules" / "thresholds.yaml")
LONG = " ".join(["слово"] * 25)


def stale_story():
    return BacklogItem.from_dict({
        "id": "S-1", "type": "story", "title": "t", "status": "open",
        "description": LONG, "parent": "E-1", "estimate": 3.0, "labels": ["mvp"],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": (NOW - timedelta(days=200)).isoformat(),
    })


def epic():
    return BacklogItem.from_dict({
        "id": "E-1", "type": "epic", "title": "e", "status": "open",
        "description": LONG,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": NOW.isoformat(),
        "extra": {"business_metric": "m", "due_date": "2026-10-01",
                  "how_to_demo": "d", "limitations": ["l"]},
    })


def test_audit_produces_findings_for_stale_story():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    rule_ids = {f.rule_id for f in result.findings}
    assert "HYG-STALE-001" in rule_ids


def test_judgment_rules_are_skipped_and_reported():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    assert set(result.skipped_rules) == {"PHS-MVP-003", "PHS-LIMIT-004", "PHS-SUP-006"}
    assert all(not f.rule_id.startswith("PHS-MVP") for f in result.findings)


def test_suppressed_finding_is_removed_and_counted():
    sup = [Suppression("HYG-STALE-001", "S-1", None)]
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, sup)
    assert result.suppressed == 1
    assert all(f.rule_id != "HYG-STALE-001" for f in result.findings)


def test_findings_sorted_by_item_then_rule():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    keys = [(f.item_id, f.rule_id) for f in result.findings]
    assert keys == sorted(keys)


def test_findings_to_dicts_is_json_ready():
    result = run_audit([epic(), stale_story()], CATALOG, PROFILE, NOW, [])
    dicts = findings_to_dicts(result.findings)
    assert set(dicts[0]) == {"rule_id", "item_id", "bucket", "severity",
                             "message", "evidence"}
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_audit.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.audit'`

- [ ] **Step 3: Реализовать движок**

`poh_backlog/audit.py`:

```python
"""Движок аудита: прогон зарегистрированных правил по элементам."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from poh_backlog.catalog import RuleSpec
from poh_backlog.context import build_context
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.profile import Profile
from poh_backlog.rules import RULES
from poh_backlog.suppress import Suppression, is_suppressed

# Правила, считающиеся на диффе снимков, а не по одному снимку.
# Их считает poh_backlog.diff, движок аудита их не трогает и не числит пропущенными.
DIFF_RULES = ("PHS-DRIFT-008",)


@dataclass(frozen=True)
class AuditResult:
    findings: list[Finding]
    skipped_rules: list[str]
    suppressed: int


def run_audit(
    items: list[BacklogItem],
    catalog: dict[str, RuleSpec],
    profile: Profile,
    now: datetime,
    suppressions: list[Suppression],
) -> AuditResult:
    ctx = build_context(items, profile, now)
    today = now.date()
    raw: list[Finding] = []
    skipped: list[str] = []

    for rule_id, spec in catalog.items():
        if rule_id in DIFF_RULES:
            continue
        if spec.kind == "judgment" or rule_id not in RULES:
            skipped.append(rule_id)
            continue
        fn = RULES[rule_id]
        for item in items:
            raw.extend(fn(item, ctx))

    kept = [f for f in raw if not is_suppressed(f, suppressions, today)]
    kept.sort(key=lambda f: (f.item_id, f.rule_id))
    return AuditResult(
        findings=kept,
        skipped_rules=sorted(skipped),
        suppressed=len(raw) - len(kept),
    )


def findings_to_dicts(findings: list[Finding]) -> list[dict]:
    return [asdict(f) for f in findings]
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_audit.py -v
```

Ожидается: 5 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: движок аудита с пропуском правил-суждений и подавлениями"
```

---

### Task 9: Снимки, дифф и дрейф фаз

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/diff.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_diff.py`

**Interfaces:**
- Consumes: `BacklogItem`, `Finding` из `poh_backlog.model`; `Profile` из `poh_backlog.profile`
- Produces: `take_snapshot(items: list[BacklogItem]) -> dict`, `DiffReport` (frozen dataclass, поля `added: list[str]`, `removed: list[str]`, `changed: dict[str, dict]`), `diff_snapshots(prev: dict | None, curr: dict) -> DiffReport`, `detect_phase_drift(prev: dict | None, items: list[BacklogItem], profile: Profile) -> list[Finding]`, `render_report_md(diff: DiffReport, findings_now: int, findings_prev: int) -> str`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_diff.py`:

```python
from poh_backlog.diff import (DiffReport, detect_phase_drift, diff_snapshots,
                              render_report_md, take_snapshot)
from poh_backlog.model import BacklogItem
from poh_backlog.profile import Profile

PROFILE = Profile({"phases": {"mvp_tag": "mvp", "grow_tag": "grow",
                              "support_label": "support"}})


def item(id_, labels=(), estimate=1.0, updated="2026-08-01T00:00:00+00:00",
         description="d"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "description": description, "labels": list(labels), "estimate": estimate,
        "parent": "E-1", "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": updated,
    })


def test_snapshot_records_labels_estimate_and_updated_at():
    snap = take_snapshot([item("S-1", labels=("mvp",))])
    assert snap["items"]["S-1"]["labels"] == ["mvp"]
    assert snap["items"]["S-1"]["estimate"] == 1.0
    assert snap["items"]["S-1"]["updated_at"] == "2026-08-01T00:00:00+00:00"


def test_diff_detects_added_removed_changed():
    prev = take_snapshot([item("S-1"), item("S-2")])
    curr = take_snapshot([item("S-1", estimate=5.0), item("S-3")])
    report = diff_snapshots(prev, curr)
    assert report.added == ["S-3"]
    assert report.removed == ["S-2"]
    assert report.changed["S-1"]["estimate"] == {"from": 1.0, "to": 5.0}


def test_diff_against_no_previous_snapshot_marks_everything_added():
    curr = take_snapshot([item("S-1")])
    report = diff_snapshots(None, curr)
    assert report.added == ["S-1"]
    assert report.removed == []
    assert report.changed == {}


def test_grow_to_mvp_without_comment_marker_flagged():
    prev = take_snapshot([item("S-1", labels=("grow",))])
    now_items = [item("S-1", labels=("mvp",))]
    findings = detect_phase_drift(prev, now_items, PROFILE)
    assert len(findings) == 1
    assert findings[0].rule_id == "PHS-DRIFT-008"
    assert findings[0].evidence == {"from": "grow", "to": "mvp"}


def test_grow_to_mvp_with_marker_in_description_not_flagged():
    prev = take_snapshot([item("S-1", labels=("grow",))])
    now_items = [item("S-1", labels=("mvp",),
                      description="Перенос в MVP: [phase-change] нужен для HowToDemo")]
    assert detect_phase_drift(prev, now_items, PROFILE) == []


def test_mvp_to_grow_not_flagged():
    prev = take_snapshot([item("S-1", labels=("mvp",))])
    now_items = [item("S-1", labels=("grow",))]
    assert detect_phase_drift(prev, now_items, PROFILE) == []


def test_report_md_contains_counts():
    report = DiffReport(added=["S-3"], removed=["S-2"], changed={"S-1": {}})
    text = render_report_md(report, findings_now=7, findings_prev=9)
    assert "Добавлено: 1" in text
    assert "Удалено: 1" in text
    assert "Изменено: 1" in text
    assert "9 -> 7" in text
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_diff.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.diff'`

- [ ] **Step 3: Реализовать снимки, дифф и дрейф**

`poh_backlog/diff.py`:

```python
"""Снимки состояния, дифф между прогонами и дрейф фаз."""
from __future__ import annotations

from dataclasses import dataclass, field

from poh_backlog.model import BacklogItem, Finding
from poh_backlog.profile import Profile

TRACKED = ("updated_at", "status", "labels", "estimate", "parent")
DRIFT_MARKER = "[phase-change]"


def take_snapshot(items: list[BacklogItem]) -> dict:
    return {"items": {
        item.id: {
            "updated_at": item.updated_at.isoformat(),
            "status": item.status,
            "labels": list(item.labels),
            "estimate": item.estimate,
            "parent": item.parent,
        }
        for item in items
    }}


@dataclass(frozen=True)
class DiffReport:
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    changed: dict[str, dict] = field(default_factory=dict)


def diff_snapshots(prev: dict | None, curr: dict) -> DiffReport:
    prev_items = (prev or {}).get("items", {})
    curr_items = curr.get("items", {})
    added = sorted(set(curr_items) - set(prev_items))
    removed = sorted(set(prev_items) - set(curr_items))
    changed: dict[str, dict] = {}
    for item_id in sorted(set(prev_items) & set(curr_items)):
        delta = {
            key: {"from": prev_items[item_id][key], "to": curr_items[item_id][key]}
            for key in TRACKED
            if prev_items[item_id].get(key) != curr_items[item_id].get(key)
        }
        if delta:
            changed[item_id] = delta
    return DiffReport(added=added, removed=removed, changed=changed)


def detect_phase_drift(prev: dict | None, items: list[BacklogItem],
                       profile: Profile) -> list[Finding]:
    prev_items = (prev or {}).get("items", {})
    mvp = profile.get("phases.mvp_tag")
    grow = profile.get("phases.grow_tag")
    findings: list[Finding] = []
    for item in items:
        before = prev_items.get(item.id)
        if before is None:
            continue
        was_grow = grow in before.get("labels", [])
        now_mvp = mvp in item.labels
        if not (was_grow and now_mvp):
            continue
        if DRIFT_MARKER in item.description:
            continue
        findings.append(Finding(
            rule_id="PHS-DRIFT-008",
            item_id=item.id,
            bucket="update",
            severity="high",
            message="История переведена из grow в mvp без обоснования",
            evidence={"from": grow, "to": mvp},
        ))
    return findings


def render_report_md(diff: DiffReport, findings_now: int, findings_prev: int) -> str:
    lines = [
        "# Изменения с прошлого прогона",
        "",
        f"- Добавлено: {len(diff.added)}",
        f"- Удалено: {len(diff.removed)}",
        f"- Изменено: {len(diff.changed)}",
        f"- Находок: {findings_prev} -> {findings_now}",
        "",
    ]
    if diff.changed:
        lines.append("## Изменённые элементы")
        lines.append("")
        for item_id, delta in diff.changed.items():
            fields = ", ".join(sorted(delta))
            lines.append(f"- `{item_id}` — поля: {fields}")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_diff.py -v
```

Ожидается: 7 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: снимки, дифф между прогонами и дрейф фаз PHS-DRIFT-008"
```

---

### Task 10: Планировщик и plan.md

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/planner.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_planner.py`

**Interfaces:**
- Consumes: `Finding`, `BacklogItem` из `poh_backlog.model`; `RuleSpec` из `poh_backlog.catalog`
- Produces: `Action` (frozen dataclass, поля `action_key: str`, `rule_id: str`, `item_id: str`, `bucket: str`, `op: str`, `rationale: str`, `expected_effect: str | None`), `Plan` (frozen dataclass, поля `actions: list[Action]`, `deferred: list[Action]`), `build_plan(findings, catalog, items, max_actions) -> Plan`, `render_plan_md(plan: Plan, run_id: str) -> str`, `plan_to_dict(plan: Plan) -> dict`, `ALLOWED_OPS: tuple[str, ...]`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_planner.py`:

```python
from pathlib import Path

from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import (ALLOWED_OPS, build_plan, plan_to_dict,
                                 render_plan_md)

CATALOG = load_catalog(Path(__file__).parent.parent / "rules" / "catalog.yaml")


def item(id_, updated="2026-08-01T00:00:00+00:00"):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": f"Заголовок {id_}", "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00", "updated_at": updated,
    })


def finding(rule_id="HYG-STALE-001", item_id="S-1", severity="medium"):
    return Finding(rule_id=rule_id, item_id=item_id, bucket="close",
                   severity=severity, message="Нет активности 200 дней", evidence={})


def test_action_key_is_stable_for_same_revision():
    items = {"S-1": item("S-1")}
    first = build_plan([finding()], CATALOG, items, max_actions=50)
    second = build_plan([finding()], CATALOG, items, max_actions=50)
    assert first.actions[0].action_key == second.actions[0].action_key


def test_action_key_changes_when_item_revision_changes():
    a = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    b = build_plan([finding()], CATALOG,
                   {"S-1": item("S-1", updated="2026-08-02T00:00:00+00:00")},
                   max_actions=50)
    assert a.actions[0].action_key != b.actions[0].action_key


def test_op_comes_from_catalog_and_is_allowed():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    assert plan.actions[0].op == "propose_close"
    assert plan.actions[0].op in ALLOWED_OPS


def test_high_severity_sorted_first():
    findings = [finding(severity="low", item_id="S-1"),
                finding(rule_id="PHS-TAG-001", severity="high", item_id="S-2")]
    items = {"S-1": item("S-1"), "S-2": item("S-2")}
    plan = build_plan(findings, CATALOG, items, max_actions=50)
    assert plan.actions[0].item_id == "S-2"


def test_cap_moves_rest_to_deferred():
    findings = [finding(item_id=f"S-{i}") for i in range(5)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(5)}
    plan = build_plan(findings, CATALOG, items, max_actions=2)
    assert len(plan.actions) == 2
    assert len(plan.deferred) == 3


def test_plan_md_lists_checkboxes_and_deferred_explicitly():
    findings = [finding(item_id=f"S-{i}") for i in range(3)]
    items = {f"S-{i}": item(f"S-{i}") for i in range(3)}
    plan = build_plan(findings, CATALOG, items, max_actions=2)
    text = render_plan_md(plan, run_id="2026-08-18-01")
    assert text.count("- [ ] ") == 2
    assert "Отложено до следующего прогона: 1" in text
    assert plan.actions[0].action_key in text


def test_plan_to_dict_round_trips_keys():
    plan = build_plan([finding()], CATALOG, {"S-1": item("S-1")}, max_actions=50)
    data = plan_to_dict(plan)
    assert set(data) == {"actions", "deferred"}
    assert set(data["actions"][0]) == {"action_key", "rule_id", "item_id", "bucket",
                                       "op", "rationale", "expected_effect"}
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_planner.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.planner'`

- [ ] **Step 3: Реализовать планировщик**

`poh_backlog/planner.py`:

```python
"""Планировщик: findings в корзины действий с ручным апрувом."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

from poh_backlog.catalog import RuleSpec
from poh_backlog.model import BacklogItem, Finding

ALLOWED_OPS = ("propose_close", "propose_merge", "update_field", "relink",
               "split", "comment")
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
BUCKET_TITLES = {
    "close": "Закрыть",
    "merge": "Объединить",
    "update": "Дозаполнить",
    "split": "Расщепить",
    "link": "Перелинковать",
    "no-action": "Без действий",
}


@dataclass(frozen=True)
class Action:
    action_key: str
    rule_id: str
    item_id: str
    bucket: str
    op: str
    rationale: str
    expected_effect: str | None


@dataclass(frozen=True)
class Plan:
    actions: list[Action] = field(default_factory=list)
    deferred: list[Action] = field(default_factory=list)


def _action_key(rule_id: str, item_id: str, revision: str) -> str:
    digest = hashlib.sha256(f"{rule_id}|{item_id}|{revision}".encode("utf-8"))
    return digest.hexdigest()[:16]


def build_plan(findings: list[Finding], catalog: dict[str, RuleSpec],
               items: dict[str, BacklogItem], max_actions: int) -> Plan:
    actions: list[Action] = []
    for finding in findings:
        spec = catalog[finding.rule_id]
        if spec.action not in ALLOWED_OPS:
            raise ValueError(f"{spec.id}: недопустимая операция {spec.action}")
        item = items.get(finding.item_id)
        revision = item.updated_at.isoformat() if item else "unknown"
        actions.append(Action(
            action_key=_action_key(finding.rule_id, finding.item_id, revision),
            rule_id=finding.rule_id,
            item_id=finding.item_id,
            bucket=finding.bucket,
            op=spec.action,
            rationale=finding.message,
            expected_effect=spec.expected_effect,
        ))

    actions.sort(key=lambda a: (
        SEVERITY_ORDER.get(catalog[a.rule_id].severity, 9), a.item_id, a.rule_id))
    return Plan(actions=actions[:max_actions], deferred=actions[max_actions:])


def render_plan_md(plan: Plan, run_id: str) -> str:
    lines = [
        f"# План наведения порядка, прогон {run_id}",
        "",
        "Снятая галочка означает отказ: действие не исполняется и попадает в",
        "`decisions.yaml` как отклонённое. Отмеченные действия исполняет host-агент.",
        "",
        f"Всего действий: {len(plan.actions)}",
        f"Отложено до следующего прогона: {len(plan.deferred)}",
        "",
    ]
    by_bucket: dict[str, list[Action]] = {}
    for action in plan.actions:
        by_bucket.setdefault(action.bucket, []).append(action)

    for bucket, bucket_actions in by_bucket.items():
        lines.append(f"## {BUCKET_TITLES.get(bucket, bucket)} ({len(bucket_actions)})")
        lines.append("")
        for action in bucket_actions:
            lines.append(
                f"- [ ] `{action.action_key}` **{action.rule_id}** "
                f"{action.item_id} — {action.op} — {action.rationale}"
            )
        lines.append("")

    if plan.deferred:
        lines.append("## Отложено потолком max_actions_per_run")
        lines.append("")
        for action in plan.deferred:
            lines.append(f"- `{action.item_id}` — {action.rule_id} — {action.op}")
        lines.append("")
    return "\n".join(lines)


def plan_to_dict(plan: Plan) -> dict:
    return {
        "actions": [asdict(a) for a in plan.actions],
        "deferred": [asdict(a) for a in plan.deferred],
    }
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_planner.py -v
```

Ожидается: 7 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: планировщик действий, plan.md с галочками и явным потолком"
```

---

### Task 11: Чтение апрува и shadow-гейт

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/approval.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_approval.py`

**Interfaces:**
- Consumes: `Plan`, `Action` из `poh_backlog.planner`
- Produces: `read_approvals(plan_md: str) -> set[str]`, `ApprovalResult` (frozen dataclass, поля `approved: list[Action]`, `rejected: list[Action]`), `split_by_approval(plan: Plan, plan_md: str, shadow: bool) -> ApprovalResult`, `rejections_to_decisions(rejected: list[Action], reason: str) -> list[dict]`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_approval.py`:

```python
from pathlib import Path

from poh_backlog.approval import (read_approvals, rejections_to_decisions,
                                  split_by_approval)
from poh_backlog.catalog import load_catalog
from poh_backlog.model import BacklogItem, Finding
from poh_backlog.planner import build_plan, render_plan_md

CATALOG = load_catalog(Path(__file__).parent.parent / "rules" / "catalog.yaml")


def item(id_):
    return BacklogItem.from_dict({
        "id": id_, "type": "story", "title": id_, "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    })


def sample_plan():
    findings = [
        Finding("HYG-STALE-001", "S-1", "close", "medium", "стухло", {}),
        Finding("HYG-STALE-001", "S-2", "close", "medium", "стухло", {}),
    ]
    items = {"S-1": item("S-1"), "S-2": item("S-2")}
    return build_plan(findings, CATALOG, items, max_actions=50)


def test_read_approvals_picks_checked_keys_only():
    text = ("- [x] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
            "- [ ] `cccc3333dddd4444` **HYG-STALE-001** S-2 — propose_close — m\n")
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_read_approvals_accepts_uppercase_marker():
    text = "- [X] `aaaa1111bbbb2222` **HYG-STALE-001** S-1 — propose_close — m\n"
    assert read_approvals(text) == {"aaaa1111bbbb2222"}


def test_split_by_approval_separates_actions():
    plan = sample_plan()
    approved_key = plan.actions[0].action_key
    text = render_plan_md(plan, "run-1").replace(
        f"- [ ] `{approved_key}`", f"- [x] `{approved_key}`")
    result = split_by_approval(plan, text, shadow=False)
    assert [a.action_key for a in result.approved] == [approved_key]
    assert len(result.rejected) == 1


def test_shadow_mode_approves_nothing():
    plan = sample_plan()
    text = render_plan_md(plan, "run-1").replace("- [ ] ", "- [x] ")
    result = split_by_approval(plan, text, shadow=True)
    assert result.approved == []
    assert len(result.rejected) == 2


def test_rejections_become_decision_entries():
    plan = sample_plan()
    entries = rejections_to_decisions(plan.actions, reason="снято человеком")
    assert entries[0]["verdict"] == "rejected"
    assert entries[0]["reason"] == "снято человеком"
    assert entries[0]["suppress_until"] == "forever"
    assert entries[0]["rule_id"] == "HYG-STALE-001"
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_approval.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.approval'`

- [ ] **Step 3: Реализовать апрув**

`poh_backlog/approval.py`:

```python
"""Гейт апрува: только отмеченные галочкой действия подлежат исполнению."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from poh_backlog.planner import Action, Plan

CHECKED = re.compile(r"^\s*-\s*\[[xX]\]\s*`([0-9a-f]{16})`", re.MULTILINE)


@dataclass(frozen=True)
class ApprovalResult:
    approved: list[Action] = field(default_factory=list)
    rejected: list[Action] = field(default_factory=list)


def read_approvals(plan_md: str) -> set[str]:
    return set(CHECKED.findall(plan_md))


def split_by_approval(plan: Plan, plan_md: str, shadow: bool) -> ApprovalResult:
    if shadow:
        return ApprovalResult(approved=[], rejected=list(plan.actions))
    keys = read_approvals(plan_md)
    approved = [a for a in plan.actions if a.action_key in keys]
    rejected = [a for a in plan.actions if a.action_key not in keys]
    return ApprovalResult(approved=approved, rejected=rejected)


def rejections_to_decisions(rejected: list[Action], reason: str) -> list[dict]:
    return [{
        "rule_id": action.rule_id,
        "item": action.item_id,
        "verdict": "rejected",
        "reason": reason,
        "suppress_until": "forever",
    } for action in rejected]
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_approval.py -v
```

Ожидается: 5 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: гейт апрува по галочкам plan.md и shadow-режим"
```

---

### Task 12: Память — state/ и штаб Backlog.md

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/memory.py`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_memory.py`

**Interfaces:**
- Consumes: `Plan`, `plan_to_dict` из `poh_backlog.planner`; `findings_to_dicts` из `poh_backlog.audit`
- Produces: `STAGES: tuple[str, ...]`, `write_state(root: Path, run_id: str, snapshot: dict, findings: list[dict], plan: dict, applied: list[str]) -> Path`, `load_latest_snapshot(root: Path) -> dict | None`, `load_latest_findings_count(root: Path) -> int`, `backlog_create_argv(run_id: str, state_dir: Path) -> list[str]`, `backlog_check_ac_argv(task_id: str, stage: str) -> list[str]`, `append_decisions(path: Path, entries: list[dict]) -> None`

- [ ] **Step 1: Написать падающие тесты**

`tests/test_memory.py`:

```python
import json
from pathlib import Path

import yaml

from poh_backlog.memory import (STAGES, append_decisions, backlog_check_ac_argv,
                                backlog_create_argv, load_latest_findings_count,
                                load_latest_snapshot, write_state)


def test_stages_match_spec():
    assert STAGES == ("audit", "diff", "plan", "approve", "apply", "verify",
                      "snapshot")


def test_write_state_creates_four_files(tmp_path):
    state_dir = write_state(tmp_path, "2026-08-18-01",
                            snapshot={"items": {}}, findings=[], plan={"actions": []},
                            applied=[])
    assert (state_dir / "items.snapshot.json").exists()
    assert (state_dir / "findings.json").exists()
    assert (state_dir / "plan.json").exists()
    assert json.loads((state_dir / "applied.json").read_text(encoding="utf-8")) == []


def test_load_latest_snapshot_returns_newest_run(tmp_path):
    write_state(tmp_path, "2026-08-17-01", {"items": {"A": {}}}, [], {}, [])
    write_state(tmp_path, "2026-08-18-01", {"items": {"B": {}}}, [], {}, [])
    assert load_latest_snapshot(tmp_path) == {"items": {"B": {}}}


def test_load_latest_snapshot_without_runs_returns_none(tmp_path):
    assert load_latest_snapshot(tmp_path) is None


def test_load_latest_findings_count(tmp_path):
    assert load_latest_findings_count(tmp_path) == 0
    write_state(tmp_path, "2026-08-17-01", {"items": {}},
                [{"rule_id": "A"}, {"rule_id": "B"}], {}, [])
    write_state(tmp_path, "2026-08-18-01", {"items": {}}, [{"rule_id": "C"}], {}, [])
    assert load_latest_findings_count(tmp_path) == 1


def test_backlog_create_argv_has_label_status_and_all_stages(tmp_path):
    argv = backlog_create_argv("2026-08-18-01", tmp_path / "state" / "2026-08-18-01")
    assert argv[:3] == ["backlog", "task", "create"]
    assert "-l" in argv and "hygiene" in argv
    assert argv[argv.index("-s") + 1] == "In Progress"
    assert argv.count("--ac") == len(STAGES)


def test_backlog_check_ac_argv_uses_one_based_stage_index():
    argv = backlog_check_ac_argv("task-7", "plan")
    assert argv == ["backlog", "task", "edit", "task-7", "--check-ac", "3"]


def test_append_decisions_merges_into_existing_file(tmp_path):
    path = tmp_path / "decisions.yaml"
    append_decisions(path, [{"rule_id": "A", "item": "S-1", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    append_decisions(path, [{"rule_id": "B", "item": "S-2", "verdict": "rejected",
                             "reason": "r", "suppress_until": "forever"}])
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [e["rule_id"] for e in entries] == ["A", "B"]
```

- [ ] **Step 2: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_memory.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.memory'`

- [ ] **Step 3: Реализовать память**

`poh_backlog/memory.py`:

```python
"""Память: артефакты state/ и штаб Backlog.md.

Штаб хранит указатель и статус, содержимое живёт в state/. Доску можно потерять:
она пересобирается из артефактов.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

STAGES = ("audit", "diff", "plan", "approve", "apply", "verify", "snapshot")


def _dump_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def write_state(root: Path, run_id: str, snapshot: dict, findings: list[dict],
                plan: dict, applied: list[str]) -> Path:
    state_dir = Path(root) / run_id
    state_dir.mkdir(parents=True, exist_ok=True)
    _dump_json(state_dir / "items.snapshot.json", snapshot)
    _dump_json(state_dir / "findings.json", findings)
    _dump_json(state_dir / "plan.json", plan)
    _dump_json(state_dir / "applied.json", applied)
    return state_dir


def load_latest_snapshot(root: Path) -> dict | None:
    root = Path(root)
    if not root.exists():
        return None
    runs = sorted(p for p in root.iterdir() if (p / "items.snapshot.json").exists())
    if not runs:
        return None
    return json.loads((runs[-1] / "items.snapshot.json").read_text(encoding="utf-8"))


def load_latest_findings_count(root: Path) -> int:
    root = Path(root)
    if not root.exists():
        return 0
    runs = sorted(p for p in root.iterdir() if (p / "findings.json").exists())
    if not runs:
        return 0
    return len(json.loads((runs[-1] / "findings.json").read_text(encoding="utf-8")))


def backlog_create_argv(run_id: str, state_dir: Path) -> list[str]:
    argv = [
        "backlog", "task", "create", f"Гигиена беклога, прогон {run_id}",
        "-l", "hygiene", "-s", "In Progress",
        "-d", f"Артефакт: {state_dir}",
    ]
    for stage in STAGES:
        argv.extend(["--ac", stage])
    return argv


def backlog_check_ac_argv(task_id: str, stage: str) -> list[str]:
    if stage not in STAGES:
        raise ValueError(f"Неизвестная стадия: {stage}")
    return ["backlog", "task", "edit", task_id, "--check-ac",
            str(STAGES.index(stage) + 1)]


def append_decisions(path: Path, entries: list[dict]) -> None:
    path = Path(path)
    existing = []
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    existing.extend(entries)
    path.write_text(
        yaml.safe_dump(existing, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Запустить тесты, убедиться что проходят**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_memory.py -v
```

Ожидается: 8 passed

- [ ] **Step 5: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: память прогонов в state/ и штаб Backlog.md"
```

---

### Task 13: CLI, маппинг GitHub и документация

**Files:**
- Create: `~/projects/poh-org/poh-backlog-skills/poh_backlog/cli.py`
- Create: `~/projects/poh-org/poh-backlog-skills/mappings/github.yaml`
- Create: `~/projects/poh-org/poh-backlog-skills/README.md`
- Create: `~/projects/poh-org/poh-backlog-skills/VISION.md`
- Create: `~/projects/poh-org/poh-backlog-skills/tests/fixtures/items.json`
- Test: `~/projects/poh-org/poh-backlog-skills/tests/test_cli.py`

**Interfaces:**
- Consumes: всё из задач 1–12
- Produces: `main(argv: list[str] | None = None) -> int`, подкоманды `run` и `approve`

- [ ] **Step 1: Написать фикстуру беклога**

`tests/fixtures/items.json`:

```json
[
  {
    "id": "I-1", "type": "initiative", "title": "Импорт данных",
    "description": "Бизнес-инициатива по загрузке внешних данных в продукт",
    "status": "open",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-08-10T00:00:00+00:00"
  },
  {
    "id": "E-1", "type": "epic", "title": "CSV-импорт", "status": "open",
    "description": "Эпик фичи с конечными границами и сроком",
    "created_at": "2026-01-05T00:00:00+00:00",
    "updated_at": "2026-08-10T00:00:00+00:00",
    "parent": "I-1",
    "extra": {"business_metric": "конверсия импорта +10%"}
  },
  {
    "id": "S-1", "type": "story", "title": "Загрузка файла", "status": "open",
    "description": "Пользователь выбирает CSV и видит предпросмотр первых строк перед подтверждением загрузки в систему",
    "created_at": "2026-01-06T00:00:00+00:00",
    "updated_at": "2026-01-06T00:00:00+00:00",
    "parent": "E-1", "labels": ["mvp"], "estimate": 3.0
  },
  {
    "id": "S-2", "type": "story", "title": "Валидация", "status": "open",
    "description": "коротко",
    "created_at": "2026-02-01T00:00:00+00:00",
    "updated_at": "2026-08-15T00:00:00+00:00",
    "parent": "E-1", "estimate": null
  }
]
```

- [ ] **Step 2: Написать падающие тесты CLI**

`tests/test_cli.py`:

```python
import json
import shutil
from pathlib import Path

import pytest

from poh_backlog.cli import main

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "items.json"


@pytest.fixture()
def workspace(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "items.json")
    return tmp_path


def run_cli(workspace, *extra):
    argv = ["run", "--items", str(workspace / "items.json"),
            "--state", str(workspace / "state"),
            "--out", str(workspace / "out"),
            "--run-id", "2026-08-18-01",
            "--now", "2026-08-18T00:00:00+00:00"]
    return main(argv + list(extra))


def test_run_writes_all_artifacts(workspace):
    assert run_cli(workspace, "--shadow") == 0
    out = workspace / "out"
    assert (out / "findings.json").exists()
    assert (out / "report.md").exists()
    assert (out / "plan.md").exists()
    assert (out / "plan.json").exists()
    assert (workspace / "state" / "2026-08-18-01" / "items.snapshot.json").exists()


def test_run_finds_known_defects_in_fixture(workspace):
    run_cli(workspace, "--shadow")
    findings = json.loads((workspace / "out" / "findings.json").read_text(encoding="utf-8"))
    rule_ids = {f["rule_id"] for f in findings}
    assert "HYG-STALE-001" in rule_ids   # S-1 не трогали с января
    assert "HYG-DESC-002" in rule_ids    # S-2 описание из одного слова
    assert "HYG-EST-003" in rule_ids     # S-2 без оценки
    assert "PHS-TAG-001" in rule_ids     # S-2 без тега фазы
    assert "PHS-EPIC-002" in rule_ids    # E-1 без due_date, how_to_demo, limitations
    assert "PHS-SUP-007" in rule_ids     # у I-1 нет Support-эпика


def test_shadow_run_reports_zero_approved(workspace, capsys):
    run_cli(workspace, "--shadow")
    assert "Утверждено: 0" in capsys.readouterr().out


def test_second_run_is_idempotent_on_action_keys(workspace):
    run_cli(workspace, "--shadow")
    first = (workspace / "out" / "plan.json").read_text(encoding="utf-8")
    run_cli(workspace, "--shadow")
    assert (workspace / "out" / "plan.json").read_text(encoding="utf-8") == first


def test_approve_without_checkboxes_yields_no_actions(workspace, capsys):
    run_cli(workspace, "--shadow")
    code = main(["approve", "--out", str(workspace / "out"),
                 "--decisions", str(workspace / "decisions.yaml")])
    assert code == 0
    assert "Утверждено: 0" in capsys.readouterr().out
    assert (workspace / "decisions.yaml").exists()


def test_approve_picks_checked_action(workspace, capsys):
    run_cli(workspace, "--shadow")
    plan_md = workspace / "out" / "plan.md"
    text = plan_md.read_text(encoding="utf-8").replace("- [ ] ", "- [x] ", 1)
    plan_md.write_text(text, encoding="utf-8")
    main(["approve", "--out", str(workspace / "out"),
          "--decisions", str(workspace / "decisions.yaml")])
    assert "Утверждено: 1" in capsys.readouterr().out
    actions = json.loads((workspace / "out" / "approved.json").read_text(encoding="utf-8"))
    assert len(actions) == 1
```

- [ ] **Step 3: Запустить тесты, убедиться что падают**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest tests/test_cli.py -v
```

Ожидается: FAIL, `ModuleNotFoundError: No module named 'poh_backlog.cli'`

- [ ] **Step 4: Реализовать CLI**

`poh_backlog/cli.py`:

```python
"""CLI решающего слоя. Ноль сетевых вызовов: вход и выход — файлы."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from poh_backlog.approval import rejections_to_decisions, split_by_approval
from poh_backlog.audit import findings_to_dicts, run_audit
from poh_backlog.catalog import load_catalog
from poh_backlog.diff import (detect_phase_drift, diff_snapshots,
                              render_report_md, take_snapshot)
from poh_backlog.memory import (append_decisions, backlog_create_argv,
                                load_latest_findings_count,
                                load_latest_snapshot, write_state)
from poh_backlog.model import BacklogItem
from poh_backlog.planner import (Action, Plan, build_plan, plan_to_dict,
                                 render_plan_md)
from poh_backlog.profile import load_profile
from poh_backlog.suppress import load_suppressions

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = PACKAGE_ROOT / "rules" / "catalog.yaml"
DEFAULT_THRESHOLDS = PACKAGE_ROOT / "rules" / "thresholds.yaml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_items(path: Path) -> list[BacklogItem]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [BacklogItem.from_dict(entry) for entry in raw]


def cmd_run(args: argparse.Namespace) -> int:
    now = datetime.fromisoformat(args.now)
    items = _load_items(args.items)
    catalog = load_catalog(args.catalog)
    profile = load_profile(args.thresholds,
                           Path(args.profile) if args.profile else None)
    suppressions = load_suppressions(Path(args.decisions))

    result = run_audit(items, catalog, profile, now, suppressions)
    prev = load_latest_snapshot(Path(args.state))
    prev_findings = load_latest_findings_count(Path(args.state))
    drift = detect_phase_drift(prev, items, profile)
    findings = sorted(result.findings + drift, key=lambda f: (f.item_id, f.rule_id))

    snapshot = take_snapshot(items)
    diff = diff_snapshots(prev, snapshot)

    by_id = {item.id: item for item in items}
    plan = build_plan(findings, catalog, by_id,
                      max_actions=profile.get("plan.max_actions_per_run"))

    out = Path(args.out)
    _write(out / "findings.json",
           json.dumps(findings_to_dicts(findings), ensure_ascii=False, indent=2))
    _write(out / "report.md", render_report_md(diff, len(findings), prev_findings))
    _write(out / "plan.md", render_plan_md(plan, args.run_id))
    _write(out / "plan.json",
           json.dumps(plan_to_dict(plan), ensure_ascii=False, indent=2))

    state_dir = write_state(Path(args.state), args.run_id, snapshot,
                            findings_to_dicts(findings), plan_to_dict(plan), [])

    print(f"Прогон {args.run_id}")
    print(f"Элементов: {len(items)}")
    print(f"Находок: {len(findings)}, подавлено: {result.suppressed}")
    print(f"Действий в плане: {len(plan.actions)}, отложено: {len(plan.deferred)}")
    print(f"Пропущено правил-суждений: {len(result.skipped_rules)} "
          f"({', '.join(result.skipped_rules)})")
    print("Утверждено: 0" if args.shadow else "Апрув: отметьте действия в plan.md")
    print(f"Штаб: {' '.join(backlog_create_argv(args.run_id, state_dir))}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    out = Path(args.out)
    data = json.loads((out / "plan.json").read_text(encoding="utf-8"))
    actions = [Action(**entry) for entry in data["actions"]]
    plan = Plan(actions=actions, deferred=[])
    plan_md = (out / "plan.md").read_text(encoding="utf-8")

    result = split_by_approval(plan, plan_md, shadow=False)
    _write(out / "approved.json",
           json.dumps([asdict(a) for a in result.approved],
                      ensure_ascii=False, indent=2))
    append_decisions(Path(args.decisions),
                     rejections_to_decisions(result.rejected,
                                             reason="снято человеком при апруве"))
    print(f"Утверждено: {len(result.approved)}")
    print(f"Отклонено: {len(result.rejected)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poh-backlog")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="аудит, дифф, план, снимок")
    run.add_argument("--items", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--state", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--now", default=datetime.now().astimezone().isoformat())
    run.add_argument("--profile", default=None)
    run.add_argument("--decisions", default="decisions.yaml")
    run.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    run.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    run.add_argument("--shadow", action="store_true",
                     help="ничего не утверждать: режим накопления разметки")
    run.set_defaults(func=cmd_run)

    approve = sub.add_parser("approve", help="прочитать галочки plan.md")
    approve.add_argument("--out", required=True)
    approve.add_argument("--decisions", default="decisions.yaml")
    approve.set_defaults(func=cmd_approve)

    args = parser.parse_args(argv)
    return args.func(args)
```

- [ ] **Step 5: Написать маппинг GitHub**

`mappings/github.yaml`:

```yaml
# Маппинг GitHub Issues в каноническую модель.
# Читает host-агент при сборке items.json. Пакет этот файл не исполняет.

source: github
fields:
  id: "GH-{number}"
  type: |
    epic если на Issue есть метка 'epic';
    initiative если есть метка 'initiative';
    bug если есть метка 'bug';
    иначе story
  title: title
  description: body
  status: "open если state == 'open', иначе closed"
  created_at: created_at
  updated_at: updated_at
  labels: "labels[].name"
  parent: "номер родительской задачи из sub-issues, в формате GH-{number}"
  estimate: "число из метки вида 'sp:3', иначе null"
extra:
  business_metric: "секция '## Бизнес-метрика' в теле Issue"
  due_date: "milestone.due_on"
  how_to_demo: "секция '## HowToDemo' в теле Issue"
  limitations: "пункты списка из секции '## Ограничения'"
```

- [ ] **Step 6: Написать README и VISION**

`README.md`:

```markdown
# poh-backlog-skills

Решающий слой гигиены беклога. Решает и помнит; в трекер не ходит.

## Что делает

Читает нормализованный `items.json`, прогоняет правила из `rules/catalog.yaml`,
выдаёт находки, отчёт об изменениях с прошлого прогона и план действий с
галочками. Исполняет план host-агент своими инструментами.

## Границы

- Ноль сетевых вызовов. Нет клиентов Jira и GitHub, нет секретов
- Ничего деструктивного: операции удаления в словаре плана нет
- Правила-суждения (`PHS-MVP-003`, `PHS-LIMIT-004`, `PHS-SUP-006`) в этом срезе
  пропускаются: они требуют модели и приходят срезом 2

## Быстрый старт

```bash
pip install -e ".[dev]"
poh-backlog run \
  --items items.json \
  --out out \
  --state state \
  --run-id 2026-08-18-01 \
  --shadow
```

Разметить план: отметить галочками нужные действия в `out/plan.md`, затем

```bash
poh-backlog approve --out out --decisions decisions.yaml
```

Утверждённое ложится в `out/approved.json`, снятое — в `decisions.yaml` как
подавление, чтобы не возвращаться следующим прогоном.

## Модель фаз

Эпик фичи владеет границей и сроком. `mvp` и `grow` — теги на историях внутри
него. Support — отдельный вечный эпик, один на бизнес-инициативу.

## Тесты

```bash
python -m pytest -v
```

Дизайн: `poh-org/docs/superpowers/specs/2026-08-18-poh-backlog-skills-design.md`
```

`VISION.md`:

```markdown
# poh-backlog-skills — Vision

> **Гигиена беклога как правила, а не как ритуал.**

## Миссия

Снять с Product Owner вычитку и нормализацию беклога. Хвосты, кривые связи,
пустые описания, протухшие приоритеты и дубли находит агент; решение остаётся
за человеком.

## Отличие от poh-issue-agents

`poh-issue-agents` реактивен: один Issue, webhook, триаж на входе.
`poh-backlog-skills` периодичен: весь беклог, аудит, дифф, план. Общее — знание:
оба читают `rules/`.

## Принципы

- **Правила — данные.** Любой потребитель на любом языке читает те же YAML
- **Решает человек.** Ни одно действие не исполняется без галочки
- **Ничего деструктивного.** Закрытие — это метка и комментарий, не удаление
- **Память важнее прогона.** Отклонённое не возвращается: `decisions.yaml`
- **Молчаливого усечения нет.** Отложенное потолком перечисляется явно
- **Зрелость по данным.** Правило выходит из `experimental` по измеренным
  порогам, а не по ощущению

## Дорожная карта срезов

1. **Срез 1 (текущий):** аудит, дифф, план, память, shadow-режим
2. Замыкание цикла: `eval`, выход правил из shadow, `verify`, автоприменение
3. Jira: маппинг Jira Server, прогон на ARM и KION
4. Декомпозиция: SPIDR, расщепление на MVP-часть и Grow-хвост
5. Метрики: backlog health, flow metrics, метрики фаз
6. Автокалибровка порогов по истории беклога
```

- [ ] **Step 7: Запустить весь набор тестов**

```bash
cd ~/projects/poh-org/poh-backlog-skills && python -m pytest -v
```

Ожидается: 6 passed в `test_cli.py`, всего 78 passed

- [ ] **Step 8: Коммит**

```bash
cd ~/projects/poh-org/poh-backlog-skills && git add -A && git commit -m "feat: CLI run и approve, маппинг GitHub, README и VISION"
```

---

## Готовность среза

После задачи 13 работают шаги демо 3, 4, 5, 6, 9 и 10. Шаг 7 исполняет
host-агент по `out/approved.json` своими инструментами. Шаг 8 в этом срезе
сводится к повторному `run` и сравнению отчётов.

Из раскладки раздела 4.3 спеки в срезе 1 осознанно не создаются:
`schemas/finding.schema.json`, `schemas/plan.schema.json`,
`schemas/profile.schema.json` — формы закреплены тестами и dataclass-ами;
`eval/`, `mappings/jira.yaml`, `skills/`, `commands/`, `install.sh`.
Штаб Backlog.md не вызывается пакетом: `run` печатает готовую команду
`backlog task create`, исполняет её host-агент — это сохраняет правило «ноль I/O».

Не входит в срез 1 и приходит срезом 2: `poh-backlog eval`, метрики качества,
выход правил из `experimental`, `verify` со сверкой `expected_effect`,
исполнение правил-суждений.
