# Срез verify (контур проверки исполнения) — фактическая почва

Репозиторий: `poh-org/poh-backlog-skills`, ветка `main`, срез 1 отгружен, 163 теста
(проверено: `python3 -m pytest -q` → `163 passed`). Контура `verify` в коде нет:
CLI сегодня имеет ровно две подкоманды — `run` и `approve`
(`poh_backlog/cli.py:168-190`, `add_subparsers`).

## Зависимости

| Направление | Компонент | Тип связи | Что передаётся | Критичность | Источник |
|---|---|---|---|---|---|
| upstream | `poh_backlog/cli.py: cmd_run` | вызов функций | `items.json` → `BacklogItem` через `_load_items` | высокая: единственная точка входа данных | `poh_backlog/cli.py:42-44` |
| upstream | `poh_backlog/catalog.py: load_catalog` | файл YAML | 12 записей `RuleSpec` (id, action, expected_effect, kind, maturity...) | высокая: без каталога `run_audit` и `build_plan` не работают | `poh_backlog/catalog.py:69-87`, `poh_backlog/data/catalog.yaml:1-149` |
| upstream | `poh_backlog/profile.py: load_profile` | файл YAML, слияние с дефолтами | `Profile` (пороги + маппинг) | средняя: `ProfileError` при неизвестном ключе останавливает `run` | `poh_backlog/profile.py:51-57` |
| upstream | `poh_backlog/memory.py: load_latest_snapshot` | файл `state/<run-id>/items.snapshot.json` | предыдущий снимок (или `None`) | высокая: без него `diff`/`detect_phase_drift` работают вслепую | `poh_backlog/memory.py:96-101` |
| upstream | `poh_backlog/suppress.py: load_suppressions` | файл `decisions.yaml` | список `Suppression(rule_id, item_id, until)` | высокая: единственный гейт подавления, применяется один раз в `cmd_run` | `poh_backlog/cli.py:70,78-90` |
| internal | `audit.py: run_audit` → `rules/hygiene.py`, `rules/phases.py` | вызов функции по имени из реестра `RULES` | `BacklogItem`, `AuditContext` → `list[Finding]` | высокая: правила регистрируются побочным эффектом импорта, порядок импорта важен | `poh_backlog/audit.py:14-22,48-56` |
| internal | `audit.py` → `catalog.RuleSpec.kind` | данные (поле YAML) | `kind: judgment` → правило пропускается, попадает в `skipped_rules` | высокая: 3 из 12 правил (`PHS-MVP-003`, `PHS-LIMIT-004`, `PHS-SUP-006`) не исполняются в срезе 1 | `poh_backlog/audit.py:51-52`, `poh_backlog/data/catalog.yaml:76-125` |
| internal | `cli.py: cmd_run` → `planner.build_plan` | вызов функции | `Finding` + `RuleSpec` → `Action` (несёт `expected_effect` из каталога) | высокая: единственное место, где `expected_effect` покидает каталог | `poh_backlog/planner.py:69-90` |
| internal | `cli.py: cmd_run` → `diff.take_snapshot`/`diff_snapshots`/`detect_phase_drift` | вызов функции | снимок полей `updated_at, status, labels, estimate, parent` + служебный `phase_change_marker_present` | высокая: `PHS-DRIFT-008` целиком считается здесь, не в `run_audit` | `poh_backlog/diff.py:13-28,55-88` |
| downstream | `cli.py: cmd_run` → `memory.write_state` | запись файлов | `items.snapshot.json`, `findings.json`, `plan.json`, `applied.json` (всегда `[]`) | высокая: единственный писатель `state/<run-id>/` | `poh_backlog/memory.py:57-65`, `poh_backlog/cli.py:110-111` |
| downstream | `cli.py: cmd_run` → файлы `out/` | запись файлов | `findings.json`, `report.md`, `plan.md`, `plan.json` | высокая | `poh_backlog/cli.py:103-108` |
| internal | `cmd_approve` → `approval.split_by_approval` | вызов функции, чтение `plan.md`+`plan.json` | галочки `[x]`/`[-]`/`[ ]` по `action_key` → `ApprovalResult` | высокая: `run_id`-сверка блокирует апрув при рассинхроне файлов | `poh_backlog/cli.py:124-153` |
| downstream | `cmd_approve` → `out/approved.json`, `decisions.yaml` | запись файлов | утверждённые `Action` целиком (включая `expected_effect`); отклонённые → подавления | высокая: `approved.json` — единственный контракт с host-агентом на исполнение | `poh_backlog/cli.py:154-159` |
| — (отсутствует) | `apply` как команда CLI | нет | host-агент исполняет `approved.json` своими инструментами вне пакета | — | `README.md:9-10`, `docs/design.md:88` |

**Что затронет появление команды `verify`:** `cli.py` (новый субпарсер и `cmd_verify`, по образцу `cmd_run`/`cmd_approve`); `memory.py` (сегодня нет функции чтения `approved.json` последнего прогона — есть только `load_latest_snapshot`/`load_latest_findings_count`, придётся добавлять симметричную функцию, и `applied.json` нужно будет реально заполнять, а не писать `[]`); `catalog.py`/`planner.py` (если `expected_effect` должен из вольного текста стать проверяемой машиной структурой); `model.py` (в канонической модели нет поля "комментарии" — часть `expected_effect` вообще не имеет источника данных для проверки, см. ниже); `STAGES` в `memory.py:17` уже включает `apply`/`verify` в шаблон задачи Backlog.md, хотя обеих команд в CLI ещё нет.

## Dataflow

**Цепочка 1 — аудит и план:**
`items.json` → `_load_items` (`cli.py:42`) → `run_audit` (правила HYG-*/PHS-*, кроме judgment и `PHS-DRIFT-008`) → `merged` находки + `detect_phase_drift` → фильтр `is_suppressed` (единственный гейт, `cli.py:78-90`) → `findings` (отсортированы) → `build_plan` → `Plan(actions, deferred)` → запись `out/findings.json`, `out/plan.md`, `out/plan.json`, `out/report.md` и `state/<run-id>/{items.snapshot.json,findings.json,plan.json,applied.json}`.
Точка потери: `applied.json` в этой цепочке всегда `[]` (`cli.py:111`) — заполнить его нечем, `apply` не существует.

**Цепочка 2 — апрув:**
`out/plan.md` (галочки человека) + `out/plan.json` (сверка `run_id`, `cli.py:134-147`) → `split_by_approval` → `approved.json` (утверждённые `Action` целиком, включая `expected_effect`) и дописывание в `decisions.yaml` (отклонённые, `suppress_until: forever`). Далее исполнение — **вне пакета**, host-агентом. `approved.json` сегодня никем внутри пакета не читается обратно — это конечная точка данных, а не промежуточная.

**Цепочка 3 — память между прогонами:**
`state/<run-id>/items.snapshot.json` пишется каждым `run`, читается следующим `run` через `load_latest_snapshot` (только для `diff_snapshots`/`detect_phase_drift`) и `load_latest_findings_count` (только число для `report.md`). `state/<run-id>/plan.json` и `findings.json` внутри `state/` пишутся, но **не читаются никаким кодом пакета** — это дублирующая копия того, что уже лежит в `out/` (само собой не единственный источник истины, поскольку `out/` перезаписывается, а `state/` — нет). `applied.json` пишется и не читается никем и никогда (`grep` по `applied` в `poh_backlog/*.py` — только `memory.py:58,64`, других упоминаний нет).

**Цепочка 4 — дрейф фаз (сквозь снимки):**
`item.labels` (снимок N) + `item.labels`, `item.description` (снимок N+1) → `detect_phase_drift` сравнивает `was_grow`/`now_mvp` и `phase_change_marker_present` (внутреннее поле снимка, не входит в `TRACKED`) → `Finding(PHS-DRIFT-008)`. Точка потери: снимок хранит только 5 полей (`TRACKED` = `updated_at, status, labels, estimate, parent`, `diff.py:9`) плюс служебный маркер; `title`, `description` (кроме маркера), `type`, `extra` (business_metric, due_date, how_to_demo, limitations) в снимок **не попадают вообще** — значит дифф между прогонами не видит изменений в этих полях, включая как раз те, что требует `PHS-EPIC-002`.

## Функциональные задачи

Что контур умеет сегодня:
- Прогнать 9 детерминированных правил (4 HYG + 4 PHS + дрейф) по элементам и выдать находки, лишённые уже отклонённых человеком (`decisions.yaml`).
- Показать дифф изменившихся элементов и число находок «было → стало» (`report.md`).
- Собрать план действий по корзинам (close/merge/update/split/link/comment), с потолком `max_actions_per_run` и явным списком отложенного.
- Дать человеку утвердить/отклонить/оставить нерешённым каждое действие через галочки в git-файле, с защитой от перезаписи размеченного плана и от рассинхрона `plan.md`/`plan.json`.
- Накопить решения человека без исполнения (`--shadow`).
- Оставить артефакт памяти `state/<run-id>/`, из которого пересобирается штаб Backlog.md.

Чего нет без `verify`:
- Нет способа узнать, действительно ли host-агент внёс правку, которую утвердил человек в `approved.json` — пакет не перечитывает трекер и не сверяет `approved.json` с новым `items.json`.
- Нет проверки `expected_effect` ни в каком виде: поле нигде не сравнивается с фактическим состоянием элемента (см. ниже).
- Нет метрики Execution fidelity из `docs/design.md:396-398` — она заявлена как цель, но кода, который бы её считал, нет.
- `applied.json` не выполняет заявленную роль журнала выполненных `action_key` (`docs/design.md:251`) — он декоративный.
- Нет идемпотентности «повторный apply — no-op», заявленной в `docs/design.md:314-316`: нет ни apply-команды, ни чтения `applied.json` для пропуска повтора.

## Факты по четырём вопросам

### `expected_effect` в каталоге правил

Все 12 записей `poh_backlog/data/catalog.yaml` содержат `expected_effect` как свободный текст на английском, описывающий желаемое состояние (например, `"item has label 'stale' and comment with rule_id"` для `HYG-STALE-001`, `poh_backlog/data/catalog.yaml:11`; `"epic has business_metric, due_date, how_to_demo, limitations"` для `PHS-EPIC-002`, строка 71). Формы записи нет — это неструктурированная строка, не JSON/DSL.

Поле читает `catalog._spec` (`poh_backlog/catalog.py:52`, `entry.get("expected_effect")`) в `RuleSpec.expected_effect`. Дальше единственный потребитель — `planner.build_plan` (`poh_backlog/planner.py:85`), который копирует его в `Action.expected_effect` без разбора и без валидации содержимого. `Action` целиком (значит, и `expected_effect`) уходит в `plan.json` (`plan_to_dict`, `planner.py:145-151`) и в `approved.json` (`asdict(a)` для каждого утверждённого действия, `cli.py:154-156`).

Не найдено (проверено `grep -rn "expected_effect" --include="*.py"`, единственные совпадения — `planner.py:33,85`, `catalog.py:38,52`, `tests/test_planner.py:81`): ни одна строка кода не парсит и не проверяет `expected_effect` против фактического состояния элемента. В `render_plan_md` (`planner.py:106-142`) поле не рендерится в текст чекбокса — человек, ставящий галочку, `expected_effect` не видит.

### Файл `applied.json`

Создаётся в `memory.write_state` (`poh_backlog/memory.py:57-65`), путь `state/<run-id>/applied.json`, единственный писатель — `_dump_json(state_dir / "applied.json", applied)` (строка 64).

Единственный вызывающий — `cli.cmd_run` (`poh_backlog/cli.py:110-111`), который передаёт литерал `[]` пятым позиционным аргументом. Аргумент `applied` нигде в кодовой базе не заполняется реальными данными — ни один код-путь не вычисляет список выполненных `action_key`.

Не найдено ни одного читателя: `grep -rn "applied" --include="*.py"` вне тестов даёт только `memory.py:58,64`. Файл существует, но с момента `write_state` до следующего прогона его никто не открывает.

### Метки элемента, каноническая модель, `take_snapshot`

Метки попадают в модель через `BacklogItem.from_dict` (`poh_backlog/model.py:46-59`): `labels=tuple(raw.get("labels") or ())` — обычный список строк из `items.json` (в маппинге GitHub — `labels[].name`, `poh_backlog/data/mappings/github.yaml:17`), без структуры и метаданных (кто/когда навесил).

В `BacklogItem` (`model.py:32-43`) нет поля "комментарии" — ни в датаклассе, ни в JSON Schema (`poh_backlog/data/schemas/backlog-item.schema.json:6-19`, там `additionalProperties: false` и полный список свойств без `comments`), ни в маппинге GitHub, ни в тестовой фикстуре (`grep -rn "comment" -ri` по `poh_backlog/*.py`, схеме, маппингу и фикстуре нашёл единственное совпадение — литерал действия `"comment"` в `catalog.py:19`, это тип операции плана, а не поле данных элемента). Комментарии треккера в канонический элемент вообще не заводятся.

`take_snapshot` (`diff.py:13-28`) сохраняет на элемент только: `updated_at`, `status`, `labels`, `estimate`, `parent` и служебный `phase_change_marker_present` (булев признак наличия `[phase-change]` в `description`, не сам текст). Теряются при записи снимка: `id` (используется только как ключ словаря), `type`, `title`, `description` (кроме маркера), `created_at`, `extra` (то есть `business_metric`, `due_date`, `how_to_demo`, `limitations` — именно то, что проверяет `PHS-EPIC-002`). `diff_snapshots` дополнительно ограничивает сравнение полей константой `TRACKED = ("updated_at", "status", "labels", "estimate", "parent")` (`diff.py:9`), так что даже если бы `extra`/`description`/`type` попали в снимок, они не сравнивались бы между прогонами без правки `TRACKED`.

### Ключ действия `action_key`

Считается в `planner._action_key` (`planner.py:50-52`): `sha256(f"{rule_id}|{item_id}|{revision}")[:16]`, где `revision = item.updated_at.isoformat()` (или `"unknown"`, если элемента нет в `items` — `planner.py:77`).

Устойчивость подтверждена тестами: при неизменном `updated_at` ключ идентичен между прогонами (`test_action_key_is_stable_for_same_revision`, `tests/test_planner.py:26-30`, и сквозной `test_second_run_is_idempotent_on_action_keys`, `tests/test_cli.py:59-63`, сверяющий побайтово `plan.json`). При изменении `item.updated_at` ключ меняется (`test_action_key_changes_when_item_revision_changes`, `tests/test_planner.py:33-38`) — это единственный трекаемый компонент ревизии; изменение `labels`/`description`/`status` без изменения `updated_at` ключ не меняет (не проверено тестом, выведено из формулы: revision берёт только `updated_at`).

Практическое следствие для `verify` [УТОЧНИТЬ, см. ниже]: любое исполнение находки трекером типично обновляет `updated_at` самого элемента, значит на следующем прогоне для того же `(rule_id, item_id)` будет вычислен **другой** `action_key`, чем тот, что лежит в `approved.json` предыдущего прогона. Спецификация `docs/design.md:314-316` предполагает сверку `action_key` через `applied.json` для идемпотентности apply — при таком поведении `revision` эта сверка ключом не сработает без дополнительной логики.

## Расхождения кода и документации

- `docs/design.md:251` описывает `applied.json` как «выполненные `action_key`» — по факту это всегда пустой список, никем не заполняемый (см. вопрос про `applied.json` выше).
- `docs/design.md:314-316` заявляет: «`action_key` пишется в `applied.json`; повтор — no-op» как механизм идемпотентности apply. Команды `apply` в CLI нет вообще, `applied.json` не читается, и, как показано выше, `action_key` меняется при изменении `updated_at`, что typически происходит именно при исполнении — то есть заявленный механизм неприменим в текущем виде.
- `docs/design.md:396-398` заявляет метрику Execution fidelity — «доля действий с подтверждённым `expected_effect`». В коде `expected_effect` нигде не сверяется с фактическим состоянием; метрика нигде не считается.
- `README.md:23-24` и `VISION.md:32-33` корректно фиксируют, что `verify` отсутствует в срезе 1 и приходит срезом 2 — здесь код и документация согласованы, расхождения нет.
- `docs/design.md:150-160`, модель фаз структуры трекера, ожидает Support-эпик и эпики фичи под инициативой — реализовано (`PHS-SUP-007`, `PHS-GROW-005`, `PHS-TAG-001`, `PHS-EPIC-002` в `rules/phases.py`), расхождений с кодом не найдено.
- `docs/plan-slice1.md:2955` фиксирует историческое число «78 passed» на момент написания этого плана; сейчас в репозитории 163 теста (`python3 -m pytest -q` → `163 passed`). Это не расхождение по существу — `plan-slice1.md` документирует пошаговый план разработки на момент его написания, а не текущее состояние; отдельные шаги того же файла (например, `docs/plan-slice1.md:2378,2389,2458,2473`) описывают код `STAGES`/`applied.json`, совпадающий с нынешним `memory.py`.

## Открытые вопросы

- [УТОЧНИТЬ, автору задания] Задание формулирует появление `verify` как «четвёртой команды CLI». Измеренный факт: сегодня в `cli.py` ровно две подкоманды (`run`, `approve`); команды `apply` не существует ни в CLI, ни где-либо в пакете — по `README.md`/`docs/design.md` исполнение выполняет host-агент своими инструментами, вне `poh-backlog`. Нужно решить: будет ли `apply` отдельной командой пакета (тогда `verify` — четвёртая) или apply остаётся вне CLI (тогда `verify` — третья) — это меняет, что именно должно появиться в `cli.py` и `memory.py`.
- [УТОЧНИТЬ, архитектору правил] `expected_effect` сегодня — вольный текст на английском без схемы. Для автоматической сверки в `verify` его придётся либо оставить как человекочитаемую подсказку (тогда `verify` не может быть автоматическим по этому полю), либо переформализовать в структуру (поле/оператор/значение) для всех 12 записей `catalog.yaml` — обратная совместимость с уже написанными формулировками не гарантирована.
- [УТОЧНИТЬ, архитектору модели данных] В канонической модели (`BacklogItem`, JSON Schema, маппинг GitHub) нет представления комментариев трекера. Три `expected_effect` из 12 явно требуют комментария (`HYG-STALE-001`, `PHS-DRIFT-008`) — без поля `comments` в `items.json`/`BacklogItem` `verify` не может проверить эту часть эффекта средствами пакета; потребуется либо расширение схемы и маппингов, либо явный отказ от проверки комментариев в `verify` среза 2.
- [УТОЧНИТЬ, архитектору idempotency-модели] Поскольку `revision` в `action_key` — это только `item.updated_at`, а исполнение действия почти всегда обновляет `updated_at`, ключ, зафиксированный в `approved.json`, скорее всего не будет существовать в каталоге находок следующего прогона под тем же значением. Нужно решить, чем `verify`/`apply` будут коррелировать «предложенное действие» с «результатом после исполнения»: по `(rule_id, item_id)` без учёта `revision`, по отдельному сохранённому снимку `approved.json` на момент апрува, или иначе.
- [УТОЧНИТЬ, автору задания] `take_snapshot`/`diff_snapshots` сегодня не видят `extra` (business_metric, due_date, how_to_demo, limitations) и полный текст `description` — только производный булев маркер `[phase-change]`. Если `verify` должен уметь замечать, что PO дозаполнил обязательные атрибуты эпика (`PHS-EPIC-002`) или описание (`HYG-DESC-002`) через дифф снимков, `TRACKED`/`take_snapshot` придётся расширять; если `verify` будет сверяться не диффом, а прямым повторным аудитом нового `items.json` (как это делает `run_audit` уже сегодня), это ограничение может быть неактуально — зависит от того, каким способом решат считать `verify`.
- [УТОЧНИТЬ, владельцу state/] `state/<run-id>/plan.json` и `state/<run-id>/findings.json` дублируют содержимое `out/plan.json`/`out/findings.json`, но сегодня не читаются никаким кодом пакета (только `items.snapshot.json` читается через `load_latest_snapshot`, только счётчик — через `load_latest_findings_count`). Не найдено, предполагается ли, что `verify` начнёт читать `state/<run-id>/plan.json` или `approved.json` как источник «что было утверждено в прошлый раз» — сегодня `approved.json` не пишется в `state/`, только в `out/`, а `out/` явно описан как перезаписываемый каталог прогона, не память.
