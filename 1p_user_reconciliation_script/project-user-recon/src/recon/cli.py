# src/recon/cli.py
import os, sys, csv, click
from .engine import reconcile
from .onepassword import list_1password_users as list_1p_users
from .okta import list_okta_users, add_user_to_group, get_okta_uid_by_login, trigger_scim_reprovision
from .scim import scim_lookup, deactivate_user_scim, scim_self_check
from .op_cli import suspend_user_cli
from .util import load_env, require, JsonLogger

@click.group()
@click.option("--json-log", is_flag=True, help="Emit JSON logs to stderr and file under out/logs/")
@click.option("--quiet", is_flag=True, help="Suppress stderr log printing (still writes file if enabled).")
@click.pass_context
def main(ctx, json_log, quiet):
    """Project User Reconciliation CLI."""
    cfg = load_env()
    require(cfg, ("OKTA_BASE_URL","OKTA_API_TOKEN","OP_SCIM_BASE_URL","OP_SCIM_BEARER_TOKEN"))
    # SCIM self-check short-circuits wrong endpoints early
    try:
        scim_self_check()
    except Exception as e:
        click.echo(f"[FATAL] SCIM self-check failed: {e}", err=True)
        sys.exit(3)
    log_path = None
    if json_log:
        os.makedirs("out/logs", exist_ok=True)
        from datetime import datetime
        log_path = f"out/logs/run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"
    ctx.obj = {
        "cfg": cfg,
        "log": JsonLogger(enable=json_log, file_path=log_path, quiet=quiet),
    }

def _dump_csv(csv_dir, name, rows, headers):
    if not csv_dir: return
    os.makedirs(csv_dir, exist_ok=True)
    path = os.path.join(csv_dir, f"{name}.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    click.echo(f"[csv] wrote: {path}")

@main.command("list-1p")
@click.option("--mock", is_flag=True, help="Use mock data for 1Password")
@click.pass_obj
def list_1p(obj, mock):
    users = list_1p_users(mock=mock)
    for u in users:
        click.echo(f"{u['email']} | {u['status']} | {u.get('id')}")
    obj["log"].info("list_1p", count=len(users))

@main.command("list-okta")
@click.option("--mock", is_flag=True, help="Use mock data for Okta")
@click.pass_obj
def list_okta(obj, mock):
    users = list_okta_users(mock=mock)
    for u in users:
        click.echo(f"{u['email']} | {u['status']}")
    obj["log"].info("list_okta", count=len(users))

@main.command("recon-dryrun")
@click.option("--op-mock", is_flag=True, help="Mock 1Password API")
@click.option("--okta-mock", is_flag=True, help="Mock Okta API")
@click.option("--csv-dir", default=None, help="Directory to write CSV output")
@click.pass_obj
def recon_dryrun(obj, op_mock, okta_mock, csv_dir):
    op_users = list_1p_users(mock=op_mock)
    okta_users = list_okta_users(mock=okta_mock)
    buckets = reconcile(op_users, okta_users)
    click.echo(f"\n=== Deprovision (IdP ACTIVE + 1P ACTIVE) ({len(buckets['to_deprov'])}) ===")
    for u in buckets["to_deprov"]:
        click.echo(f"{u['email']} | {u['status']} | {u['idp_status']} | {u.get('id')}")
    click.echo(f"\n=== SCIM Onboard (not SCIM-managed + IdP ACTIVE + 1P ACTIVE) ({len(buckets['to_scim_onboard'])}) ===")
    for u in buckets["to_scim_onboard"]:
        click.echo(f"{u['email']} | {u['status']} | {u['idp_status']} | {u.get('id')}")
    click.echo(f"\n=== Provision (IdP ACTIVE + missing in 1P) ({len(buckets['to_provision'])}) ===")
    for u in buckets["to_provision"]:
        click.echo(f"{u['email']} | {u['status']} | {u['idp_status']} | {u.get('id')}")
    click.echo(f"\n=== In 1Password but NOT in IdP (legacy/unmanaged) ({len(buckets['in_1p_not_in_idp'])}) ===")
    for u in buckets["in_1p_not_in_idp"]:
        click.echo(f"{u['email']} | {u['status']} | {u.get('id')}")
    _dump_csv(csv_dir, "to_deprovision",   buckets["to_deprov"],          ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "to_scim_onboard",  buckets["to_scim_onboard"],    ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "to_provision",     buckets["to_provision"],       ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "in_1p_not_in_idp", buckets["in_1p_not_in_idp"],   ["email", "status", "id"])
    obj["log"].info("recon", sizes={k: len(v) for k, v in buckets.items()})

@main.command("apply-deprovision")
@click.option("--op-mock", is_flag=True, help="Mock 1Password API")
@click.option("--okta-mock", is_flag=True, help="Mock Okta API")
@click.option("--execute", is_flag=True, help="Actually make changes")
@click.option("--no-cli", is_flag=True, help="Disable CLI fallback")
@click.option("--csv-dir", default=None, help="Directory to write CSV output")
@click.pass_obj
def apply_deprovision(obj, op_mock, okta_mock, execute, no_cli, csv_dir):
    op_users = list_1p_users(mock=op_mock)
    okta_users = list_okta_users(mock=okta_mock)
    buckets = reconcile(op_users, okta_users)
    _dump_csv(csv_dir, "to_deprovision",   buckets["to_deprov"],          ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "to_scim_onboard",  buckets["to_scim_onboard"],    ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "to_provision",     buckets["to_provision"],       ["email", "status", "idp_status", "id"])
    _dump_csv(csv_dir, "in_1p_not_in_idp", buckets["in_1p_not_in_idp"],   ["email", "status", "id"])
    targets = buckets["to_deprov"]
    if not targets:
        click.echo("No users to deprovision."); return
    fallback_account = os.getenv("OP_ACCOUNT") or "idanrouch.b5test.eu"
    click.echo(f"Processing {len(targets)} user(s) (execute={bool(execute)}, no_cli={bool(no_cli)})…")
    scim_count = cli_count = err_count = 0
    for u in targets:
        email = u["email"]
        probe = scim_lookup(email)
        if probe.get("found"):
            if execute:
                res = deactivate_user_scim(email, dry_run=False)
                code = res.get("status_code")
                if code is not None and code < 400:
                    click.echo(f"[SCIM] Deactivated: {email} (HTTP {code})"); scim_count += 1
                    obj["log"].info("deprov_scim", email=email, code=code)
                else:
                    click.echo(f"[SCIM ERROR] {email}: {res.get('error') or res}")
                    obj["log"].error("deprov_scim_error", email=email, err=res.get("error"))
                    if not no_cli:
                        try:
                            suspend_user_cli(email, account=fallback_account, dry_run=False)
                            click.echo(f"[CLI] Suspended: {email} [{fallback_account}]"); cli_count += 1
                            obj["log"].info("deprov_cli", email=email)
                        except Exception as e:
                            click.echo(f"[CLI ERROR] {email}: {e}"); err_count += 1
                            obj["log"].error("deprov_cli_error", email=email, err=str(e))
                    else:
                        err_count += 1
            else:
                click.echo(f"[DRY RUN][SCIM] Would deactivate: {email}"); scim_count += 1
        else:
            if no_cli:
                click.echo(f"[SKIP][No SCIM][--no-cli] {email}"); err_count += 1
            else:
                if execute:
                    try:
                        suspend_user_cli(email, account=fallback_account, dry_run=False)
                        click.echo(f"[CLI] Suspended: {email} [{fallback_account}]"); cli_count += 1
                        obj["log"].info("deprov_cli", email=email)
                    except Exception as e:
                        click.echo(f"[CLI ERROR] {email}: {e}"); err_count += 1
                        obj["log"].error("deprov_cli_error", email=email, err=str(e))
                else:
                    click.echo(f"[DRY RUN][CLI] Would suspend: {email} [{fallback_account}]"); cli_count += 1
    click.echo(f"\nSummary: {scim_count} SCIM, {cli_count} CLI, {err_count} unresolved/errors")

@main.command("apply-scim-onboard")
@click.option("--op-mock", is_flag=True, help="Mock 1Password API")
@click.option("--okta-mock", is_flag=True, help="Mock Okta API")
@click.option("--okta-group-id", default=lambda: os.getenv("OKTA_SCIM_GROUP_ID", ""), help="Okta group ID for the 1Password SCIM app")
@click.option("--execute", is_flag=True, help="Actually add users to the Okta SCIM group")
@click.option("--csv-dir", default=None, help="Optional CSV snapshot dir")
@click.pass_obj
def apply_scim_onboard(obj, op_mock, okta_mock, okta_group_id, execute, csv_dir):
    if not okta_group_id:
        raise click.UsageError("Provide --okta-group-id or set OKTA_SCIM_GROUP_ID in .env")
    op_users = list_1p_users(mock=op_mock)
    okta_users = list_okta_users(mock=okta_mock)
    buckets = reconcile(op_users, okta_users)
    _dump_csv(csv_dir, "to_scim_onboard", buckets["to_scim_onboard"], ["email", "status", "idp_status", "id"])
    targets = buckets["to_scim_onboard"]
    if not targets:
        click.echo("No users to SCIM-onboard."); return
    okta_id_by_email = {u["email"].lower(): u.get("id") for u in okta_users if u.get("email") and u.get("id")}
    click.echo(f"Processing {len(targets)} user(s) (execute={bool(execute)}) into Okta group {okta_group_id}…")
    ok_count = err_count = 0
    for u in targets:
        email = u["email"].lower()
        okta_uid = okta_id_by_email.get(email) or get_okta_uid_by_login(email)
        if not okta_uid:
            click.echo(f"- SKIP {email}: no Okta userId found"); err_count += 1; continue
        if execute:
            try:
                add_user_to_group(okta_group_id, okta_uid, mock=okta_mock)
                click.echo(f"- ADDED {email} → group {okta_group_id}"); ok_count += 1
                obj["log"].info("onboard_add", email=email, group=okta_group_id)
            except Exception as e:
                click.echo(f"- ERROR {email}: {e}"); err_count += 1
                obj["log"].error("onboard_add_error", email=email, err=str(e))
        else:
            click.echo(f"- DRY RUN: would add {email} → group {okta_group_id}"); ok_count += 1
    click.echo(f"Summary: {ok_count} ok, {err_count} errors")

@main.command("reprovision")
@click.option("--email", required=True, help="User email (Okta profile.login)")
@click.option("--okta-group-id", default=lambda: os.getenv("OKTA_SCIM_GROUP_ID", ""), help="Okta group ID tied to the 1Password SCIM app")
@click.option("--mock", is_flag=True, help="Mock Okta calls")
@click.option("--wait-seconds", default=30, show_default=True, help="Poll SCIM for up to N seconds after triggering.")
@click.option("--interval", default=5, show_default=True, help="Polling interval seconds.")
@click.pass_obj
def reprovision(obj, email, okta_group_id, mock, wait_seconds, interval):
    if not okta_group_id:
        raise click.UsageError("Provide --okta-group-id or set OKTA_SCIM_GROUP_ID in .env")
    click.echo(f"[lookup] Resolving Okta UID for {email}…")
    uid = get_okta_uid_by_login(email)
    if not uid:
        click.echo(f"[error] Okta UID not found for {email}"); sys.exit(1)
    click.echo(f"[ok] Okta UID: {uid}")
    click.echo(f"[action] Toggling group {okta_group_id} to trigger SCIM…")
    res = trigger_scim_reprovision(okta_group_id, email, mock=mock)
    if not res.get("ok"):
        click.echo(f"[error] {res.get('error')}"); sys.exit(2)
    click.echo("[ok] Group toggle complete.")
    click.echo("[verify] Checking 1Password SCIM presence…")
    if wait_seconds and not mock:
        import time
        deadline = time.time() + max(0, wait_seconds)
        while time.time() < deadline:
            probe = scim_lookup(email)
            if probe.get("found"):
                click.echo(f"[ok] SCIM user exists (id={probe.get('user_id')})")
                obj["log"].info("reprov_ok", email=email, user_id=probe.get("user_id"))
                break
            time.sleep(max(1, interval))
        else:
            click.echo("[warn] SCIM user not found yet. Provisioning may still be in flight.")
            obj["log"].warn("reprov_pending", email=email)
    else:
        probe = scim_lookup(email)
        if probe.get("found"):
            click.echo(f"[ok] SCIM user exists (id={probe.get('user_id')})")
            obj["log"].info("reprov_ok", email=email, user_id=probe.get("user_id"))
        else:
            click.echo("[warn] SCIM user not found yet. Provisioning may still be in flight.")
            obj["log"].warn("reprov_pending", email=email)

@main.command("reprovision-batch")
@click.option("--csv", "csv_path", required=True, help="CSV with a header 'email'")
@click.option("--okta-group-id", default=lambda: os.getenv("OKTA_SCIM_GROUP_ID", ""))
@click.option("--mock", is_flag=True)
@click.pass_obj
def reprovision_batch(obj, csv_path, okta_group_id, mock):
    if not okta_group_id:
        raise click.UsageError("Provide --okta-group-id or set OKTA_SCIM_GROUP_ID in .env")
    import csv as _csv
    with open(csv_path, newline="", encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    ok = err = 0
    for row in rows:
        email = (row.get("email") or "").strip()
        if not email: continue
        res = trigger_scim_reprovision(okta_group_id, email, mock=mock)
        if res.get("ok"): ok += 1
        else:
            err += 1; click.echo(f"- ERROR {email}: {res.get('error')}")
    click.echo(f"Summary: {ok} ok, {err} errors")

if __name__ == "__main__":
    main()
