"""CLI решающего слоя. Ноль сетевых вызовов: вход и выход — файлы."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from poh_backlog.approval import (has_decisions, rejections_to_decisions,
                                  split_by_approval)
from poh_backlog.audit import findings_to_dicts, run_audit
from poh_backlog.catalog import load_catalog
from poh_backlog.diff import (detect_phase_drift, diff_snapshots,
                              render_report_md, take_snapshot)
from poh_backlog.memory import (StateError, append_decisions,
                                backlog_create_argv, carry_forward_verdicts,
                                load_latest_findings_count,
                                load_latest_snapshot, load_latest_verdicts,
                                write_state, write_verdicts)
from poh_backlog.model import BacklogItem, ensure_aware
from poh_backlog.planner import (Action, Plan, build_plan, plan_to_dict,
                                 promised_actions, read_run_id, render_plan_md)
from poh_backlog.profile import load_profile
from poh_backlog.suppress import (DecisionsError, is_pair_suppressed,
                                  is_suppressed, load_suppressions)
from poh_backlog.verify import render_verify_md, verdicts_to_dicts, verify_actions

# Каталог самого пакета, а не репозитория: rules/, prompts/, mappings/ и
# schemas/ раньше лежали в корне репозитория, вне пакета poh_backlog, и
# обычная (не editable) установка не копировала их в site-packages/ вообще —
# только сам пакет. Теперь данные лежат внутри пакета (poh_backlog/data/) и
# разрешаются относительно каталога самого пакета, а не его родителя.
PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_CATALOG = PACKAGE_ROOT / "data" / "catalog.yaml"
DEFAULT_THRESHOLDS = PACKAGE_ROOT / "data" / "thresholds.yaml"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _load_items(path: Path) -> list[BacklogItem]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [BacklogItem.from_dict(entry) for entry in raw]


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    plan_md_path = out / "plan.md"
    if plan_md_path.exists():
        existing_plan_md = plan_md_path.read_text(encoding="utf-8")
        if has_decisions(existing_plan_md):
            # PO мог уже проставить галочки или явные отказы в этом plan.md.
            # Безусловная перезапись (например, из ночного cron) молча
            # уничтожила бы эти решения. Нетронутый план (в нём нет ни одной
            # отметки) перезаписывать безопасно — там нечего терять.
            print(
                f"{plan_md_path} содержит непустые решения (галочки [x] или "
                f"отказы [-]) и не будет перезаписан. Сначала выполните "
                f"'approve' для этого прогона, либо укажите другой --out.",
                file=sys.stderr,
            )
            return 2

    now = ensure_aware(datetime.fromisoformat(args.now))
    items = _load_items(args.items)
    catalog = load_catalog(args.catalog)
    profile = load_profile(args.thresholds,
                           Path(args.profile) if args.profile else None)
    suppressions = load_suppressions(Path(args.decisions))

    result = run_audit(items, catalog, profile, now, suppressions)
    prev = load_latest_snapshot(Path(args.state))
    prev_findings = load_latest_findings_count(Path(args.state))
    drift = detect_phase_drift(prev, items, profile)
    today = now.date()

    # Единственный гейт подавления: каждая находка, вошедшая в findings —
    # хоть из аудита, хоть из дрейфа фаз — проходит через is_suppressed
    # именно здесь. Раньше drift-находки склеивались с уже отфильтрованными
    # находками аудита без повторной проверки, и отклонённый PHS-DRIFT-008
    # возвращался как новый на каждом прогоне.
    merged = result.findings + drift
    findings = sorted(
        (f for f in merged if not is_suppressed(f, suppressions, today)),
        key=lambda f: (f.item_id, f.rule_id),
    )
    drift_suppressed = sum(
        1 for f in drift if is_suppressed(f, suppressions, today))
    suppressed_total = result.suppressed + drift_suppressed

    snapshot = take_snapshot(items)
    diff = diff_snapshots(prev, snapshot)

    by_id = {item.id: item for item in items}
    plan = build_plan(findings, catalog, by_id,
                      max_actions=profile.get("plan.max_actions_per_run"))
    # run_id и shadow этого прогона привязываются к плану здесь: build_plan
    # их не знает, но approve обязан прочитать их из plan.json, а не
    # довериться собственному, отдельно переданному флагу (B2, B4).
    plan = replace(plan, run_id=args.run_id, shadow=args.shadow)

    # Неисполненное с прошлой проверки возвращается в план: действие, которое
    # PO утвердил и которое никто не сделал, иначе теряется бесследно.
    # Дедупликация по ключу: если та же находка пришла и свежей (а это
    # рутинный случай — host ничего не менял, элемент той же ревизии, значит
    # правило перепрогонится на те же rule_id/item_id/revision и даст тот же
    # action_key), действие не должно задвоиться. Побеждает обещанная копия,
    # а не свежая: только у неё есть promised_from, без которого «Обещано,
    # не сделано» не покажет, что решение уже когда-то принималось.
    # promised_from должен указывать на прогон, где действие утверждали, а не
    # на текущий, поэтому идентификатор берётся из той же пары, что и вердикты.
    verdicts_run_id, verdicts = load_latest_verdicts(Path(args.state))
    promised = promised_actions(verdicts, catalog, by_id,
                                verdicts_run_id or args.run_id)
    # Единственный гейт подавления (см. комментарий выше про findings) обязан
    # закрывать и этот, второй вход в plan.actions: без этой фильтрации явный
    # `[-]` на вернувшемся обещании ничего не значил — approve писал в
    # decisions.yaml подавление, но promised_actions его не читает, и
    # отклонённое навсегда действие возвращалось на каждом следующем прогоне.
    promised = [a for a in promised
               if not is_pair_suppressed(a.rule_id, a.item_id, suppressions, today)]
    promised_keys = {a.action_key for a in promised}
    # Дедупликация против deferred, а не только против actions: находка,
    # утверждённая раньше и не исполненная, могла в этом прогоне снова
    # сработать и попасть за потолок max_actions_per_run — без вычёркивания
    # из deferred план одновременно называл её и «обещано, не сделано» с
    # пустой галочкой, и «отложено потолком», хотя это одно и то же действие.
    fresh = [a for a in plan.actions if a.action_key not in promised_keys]
    fresh_deferred = [a for a in plan.deferred if a.action_key not in promised_keys]
    plan = replace(plan, actions=promised + fresh, deferred=fresh_deferred)

    _write(out / "findings.json",
           json.dumps(findings_to_dicts(findings), ensure_ascii=False, indent=2) + "\n")
    _write(out / "report.md", render_report_md(diff, len(findings), prev_findings))
    _write(out / "plan.md", render_plan_md(plan, args.run_id))
    _write(out / "plan.json",
           json.dumps(plan_to_dict(plan), ensure_ascii=False, indent=2) + "\n")

    state_dir = write_state(Path(args.state), args.run_id, snapshot,
                            findings_to_dicts(findings), plan_to_dict(plan), [])

    print(f"Прогон {args.run_id}")
    print(f"Элементов: {len(items)}")
    print(f"Находок: {len(findings)}, подавлено: {suppressed_total}")
    promised_count = sum(1 for a in plan.actions if a.promised_from is not None)
    print(f"Действий в плане: {len(plan.actions)}, отложено: {len(plan.deferred)}")
    if promised_count:
        print(f"Из них обещано ранее и не исполнено: {promised_count}")
    print(f"Пропущено правил-суждений: {len(result.skipped_rules)} "
          f"({', '.join(result.skipped_rules)})")
    print("Утверждено: 0" if args.shadow else "Апрув: отметьте действия в plan.md")
    print(f"Штаб: {' '.join(backlog_create_argv(args.run_id, state_dir))}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    out = Path(args.out)
    plan_json_path = out / "plan.json"
    plan_md_path = out / "plan.md"
    data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    actions = [Action(**entry) for entry in data["actions"]]
    plan = Plan(actions=actions, deferred=[],
               run_id=data.get("run_id"), shadow=data.get("shadow", False))
    plan_md = plan_md_path.read_text(encoding="utf-8")

    plan_md_run_id = read_run_id(plan_md)
    if plan_md_run_id != plan.run_id:
        # plan.md и plan.json ничем формально не связаны, кроме этой метки:
        # если plan.md перезаписан более новым прогоном, галочки в нём
        # относятся уже не к тому plan.json, что лежит рядом. Утверждать их
        # в этой ситуации небезопасно.
        print(
            f"{plan_md_path} относится к прогону {plan_md_run_id!r}, а "
            f"{plan_json_path} — к прогону {plan.run_id!r}. Похоже, файлы "
            f"рассинхронизированы (plan.md перезаписан другим прогоном); "
            f"апрув отменён.",
            file=sys.stderr,
        )
        return 2

    # shadow — это флаг прогона, породившего план, а не параметр approve:
    # человек не должен суметь утвердить план shadow-прогона, забыв
    # какой-то свой собственный флаг — поэтому approve берёт shadow из
    # plan.json, а не откуда-либо ещё.
    result = split_by_approval(plan, plan_md, shadow=plan.shadow)
    _write(out / "approved.json",
           json.dumps([asdict(a) for a in result.approved],
                      ensure_ascii=False, indent=2) + "\n")
    append_decisions(Path(args.decisions),
                     rejections_to_decisions(result.rejected,
                                             reason="явно отклонено человеком при апруве"))
    print(f"Утверждено: {len(result.approved)}")
    print(f"Отклонено: {len(result.rejected)}")
    print(f"Не решено: {len(result.undecided)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    out = Path(args.out)
    approved_path = out / "approved.json"
    plan_json_path = out / "plan.json"
    if not approved_path.exists():
        print(
            f"{approved_path} не найден: проверять нечего. Сначала выполните "
            f"'approve' для этого прогона.",
            file=sys.stderr,
        )
        return 2

    approved = json.loads(approved_path.read_text(encoding="utf-8"))

    if not plan_json_path.exists():
        print(
            f"{plan_json_path} не найден: определить run_id для проверки "
            f"нечем. Сначала выполните 'run' для этого прогона.",
            file=sys.stderr,
        )
        return 2
    try:
        plan_data = json.loads(plan_json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(
            f"{plan_json_path} повреждён (некорректный JSON): проверка "
            f"отменена.",
            file=sys.stderr,
        )
        return 2

    run_id = plan_data.get("run_id")
    if not run_id:
        print(f"{plan_json_path} не содержит run_id; проверка отменена.",
              file=sys.stderr)
        return 2

    now = ensure_aware(datetime.fromisoformat(args.now))
    items = _load_items(args.items)
    catalog = load_catalog(args.catalog)
    profile = load_profile(args.thresholds,
                           Path(args.profile) if args.profile else None)
    suppressions = load_suppressions(Path(args.decisions))
    today = now.date()

    state_dir = Path(args.state) / run_id
    snapshot_path = state_dir / "items.snapshot.json"
    prev_snapshot = None
    if snapshot_path.exists():
        prev_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))

    # Журнал обещаний — до записи вердиктов этого прогона: load_latest_verdicts
    # смотрит на последний прогон, где verdicts.json вообще писался, а этот
    # прогон свой ещё не записал, так что это ровно прошлое состояние
    # журнала.
    _, previous_verdicts = load_latest_verdicts(Path(args.state))

    result = verify_actions(approved, items, catalog, profile, now, prev_snapshot)
    _write(out / "verify.md", render_verify_md(result, run_id))

    # Журнал накопительный, а не снимок: пара из прошлого прогона, которую
    # approved.json этого прогона не покрыл, переносится как есть — иначе
    # прогон, где approve ничего не утвердил, стирает обещание, которое
    # никто не отклонял и не подавлял (финальное ревью, находка 2).
    carried = carry_forward_verdicts(previous_verdicts, approved, suppressions, today)
    ledger = verdicts_to_dicts(result.verdicts) + carried
    write_verdicts(Path(args.state), run_id, ledger,
                   [v.action_key for v in result.verdicts if v.status == "done"])

    percent = round(result.fidelity * 100)
    print(f"Проверка прогона {run_id}")
    print(f"Действий проверено: {len(result.verdicts)}")
    print(f"Достоверность исполнения: {percent}%")
    if prev_snapshot is None:
        print("Снимок «до» не найден: раздел побочного урона пропущен")
    else:
        print(f"Изменено вне плана: {len(result.collateral)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="poh-backlog")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="аудит, дифф, план, снимок")
    run.add_argument("--items", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--state", required=True)
    run.add_argument("--run-id", required=True)
    run.add_argument("--now", default=datetime.now().astimezone().isoformat(),
                     help="момент времени для аудита в формате ISO 8601; "
                          "значение без указания часового пояса трактуется "
                          "как UTC")
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

    verify_cmd = sub.add_parser("verify", help="проверить, что утверждённое исполнено")
    verify_cmd.add_argument("--items", required=True,
                            help="свежий срез беклога после исполнения")
    verify_cmd.add_argument("--out", required=True)
    verify_cmd.add_argument("--state", required=True)
    verify_cmd.add_argument("--now", default=datetime.now().astimezone().isoformat(),
                            help="момент проверки; без смещения трактуется как UTC")
    verify_cmd.add_argument("--profile", default=None)
    verify_cmd.add_argument("--decisions", default="decisions.yaml",
                            help="нужен для переноса и подавления пар в "
                                 "накопительном журнале обещаний (verdicts.json)")
    verify_cmd.add_argument("--catalog", default=str(DEFAULT_CATALOG))
    verify_cmd.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    verify_cmd.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (StateError, DecisionsError) as exc:
        # Память прогонов и decisions.yaml редактируются или трогаются руками:
        # битый файл — реалистичный случай, а не повод ронять человека,
        # запустившего это из cron, в сырой traceback.
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
