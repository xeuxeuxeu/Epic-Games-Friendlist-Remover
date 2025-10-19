#!/usr/bin/env python3
import base64
import sys
import time
from typing import Dict, Iterable, List, Sequence, Tuple

import requests
from requests import HTTPError

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.prompt import Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn

try:
    import readchar
    from readchar import key as readchar_key
except Exception:  # pragma: no cover
    print("Missing dependency: readchar\nInstall with: pip install readchar", file=sys.stderr)
    sys.exit(1)

TIMEOUT_IN_SECONDS = 10
CLIENT = b"98f7e42c2e3a4f86a74eb43fbb41ed39:0a2449a2-001a-451e-afec-3e812901c4d7"


def _chunked(seq: Sequence[str], n: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def _normalize_account_id(raw: str) -> str:
    if ":" in raw:
        return raw.split(":", 1)[1]
    return raw


class EpicFriendsUI:

    def __init__(self, console: Console) -> None:
        self.console = console

    def _render_table(
        self,
        rows: List[Dict[str, str]],
        selected_ids: set,
        cursor_index: int,
        viewport_size: int,
    ) -> Panel:
        # Constrain table width so it doesn't stretch the entire console
        max_width = max(60, min(90, self.console.size.width - 20))

        table = Table(
            show_header=True,
            header_style="bold cyan",
            box=None,
            width=max_width,
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Sel", width=5, no_wrap=True, justify="center")
        table.add_column("Display Name", overflow="fold", max_width=max_width - 40)
        table.add_column("Mutual", justify="right", width=8, no_wrap=True)
        table.add_column("Since", width=22, overflow="fold", no_wrap=True)

        start = 0 if len(rows) <= viewport_size else max(0, min(cursor_index - viewport_size // 2, len(rows) - viewport_size))
        end = len(rows) if len(rows) <= viewport_size else start + viewport_size

        for idx in range(start, end):
            r = rows[idx]
            is_current = idx == cursor_index
            is_selected = r["accountId"] in selected_ids

            sel = "[green]x[/]" if is_selected else "[grey42] [/]"

            row_style = ""
            if is_current and is_selected:
                row_style = "bold white on dark_green"
            elif is_current:
                row_style = "bold white on grey23"
            elif is_selected:
                row_style = "green"

            table.add_row(
                sel,
                r["displayName"],
                str(r.get("mutual", "")),
                r.get("created", "")[:19].replace("T", " "),
                style=row_style,
                end_section=False,
            )

        help_text = "[b]↑/↓[/] move  •  [b]X[/] select/unselect  •  [b]Enter[/] confirm  •  [b]Q[/] cancel"
        return Panel(table, title="Friends (interactive)", border_style="cyan", subtitle=help_text, padding=(1, 1))

    def select(self, rows: List[Dict[str, str]], viewport_size: int = 14) -> List[str]:
        if not rows:
            return []

        cursor_index = 0
        selected_ids: set = set()

        with Live(self._render_table(rows, selected_ids, cursor_index, viewport_size), console=self.console, refresh_per_second=30, screen=False) as live:
            while True:
                ch = readchar.readkey()
                if ch == readchar_key.UP:
                    cursor_index = (cursor_index - 1) % len(rows)
                elif ch == readchar_key.DOWN:
                    cursor_index = (cursor_index + 1) % len(rows)
                elif ch in ("x", "X"):
                    acc_id = rows[cursor_index]["accountId"]
                    if acc_id in selected_ids:
                        selected_ids.remove(acc_id)
                    else:
                        selected_ids.add(acc_id)
                elif ch == readchar_key.ENTER:
                    return list(selected_ids)
                elif ch in ("q", "Q", readchar_key.CTRL_C, readchar_key.CTRL_D):
                    return []
                # re-render
                live.update(self._render_table(rows, selected_ids, cursor_index, viewport_size))


class FriendsRemover:
    def __init__(self) -> None:
        self.client_basic = base64.b64encode(CLIENT).decode("utf-8")
        self.session = requests.Session()
        self.account_id: str = ""
        self.user_bearer: str = ""  # user token obtained from device_code flow
        self.console = Console()


    def token_client_credentials(self) -> Dict:
        headers = {"Authorization": f"basic {self.client_basic}"}
        body = {"grant_type": "client_credentials"}
        resp = self.session.post(
            "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
            headers=headers,
            data=body,
            timeout=TIMEOUT_IN_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def create_device_code(self, bearer_token: str) -> Dict:

        headers = {"Authorization": f"bearer {bearer_token}"}
        resp = self.session.post(
            "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/deviceAuthorization",
            headers=headers,
            timeout=TIMEOUT_IN_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def exchange_device_code_for_user_token(self, device_code: str, *, max_wait_seconds: int = 180) -> Dict:

        headers = {"Authorization": f"basic {self.client_basic}"}
        body = {"grant_type": "device_code", "device_code": device_code}

        start = time.time()
        while True:
            resp = self.session.post(
                "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token",
                headers=headers,
                data=body,
                timeout=TIMEOUT_IN_SECONDS,
            )
            if resp.status_code == 200:
                return resp.json()


            if resp.status_code in (400, 401, 403):
                try:
                    payload = resp.json()
                except Exception:
                    payload = {}
                err = (payload or {}).get("error", "")
                if err in {"authorization_pending", "invalid_grant", "slow_down"} and (time.time() - start) < max_wait_seconds:
                    time.sleep(2)
                    continue

            resp.raise_for_status()


    def get_friends_summary(self) -> Dict:

        headers = {"Authorization": f"bearer {self.user_bearer}"}
        resp = self.session.get(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{self.account_id}/summary",
            headers=headers,
            timeout=TIMEOUT_IN_SECONDS,
        )
        resp.raise_for_status()
        return resp.json()

    def resolve_display_names(self, account_ids: Sequence[str]) -> Dict[str, str]:

        headers = {"Authorization": f"bearer {self.user_bearer}"}
        out: Dict[str, str] = {}

        for batch in _chunked(list(account_ids), 100):
            normalized = [_normalize_account_id(a) for a in batch]
            joined = "&accountId=".join(normalized)
            url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account?locale=en&accountId={joined}"

            resp = self.session.get(url, headers=headers, timeout=TIMEOUT_IN_SECONDS)
            resp.raise_for_status()

            data = resp.json()
           
            if isinstance(data, dict) and data.get("id"):
                data = [data]

            if isinstance(data, list):
                for item in data:
                    aid = item.get("id") or item.get("accountId") or ""
                    dname = item.get("displayName") or item.get("display_name") or "<unknown>"
                    if aid:
                        out[aid] = dname
            else:

                pass

        return out

    def remove_friend(self, friend_account_id: str) -> None:
        """
        Remove a single friend by account id.
        """
        headers = {"Authorization": f"bearer {self.user_bearer}"}
        resp = self.session.delete(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{self.account_id}/friends/{friend_account_id}",
            headers=headers,
            timeout=TIMEOUT_IN_SECONDS,
        )

        if resp.status_code not in (200, 202, 204):
            resp.raise_for_status()

    def clear_all_friends(self) -> None:
        """
        Clear the entire friends list (uses the bulk clear endpoint).
        """
        headers = {"Authorization": f"bearer {self.user_bearer}"}
        resp = self.session.delete(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{self.account_id}/friends",
            headers=headers,
            timeout=TIMEOUT_IN_SECONDS,
        )
        if resp.status_code not in (200, 202, 204):
            resp.raise_for_status()

    def kill_session(self) -> None:
        """
        Kill the OAuth session using the *user* bearer token.
        """
        headers = {"Authorization": f"bearer {self.user_bearer}"}
        resp = self.session.delete(
            f"https://account-public-service-prod.ol.epicgames.com/account/api/oauth/sessions/kill/{self.user_bearer}",
            headers=headers,
            timeout=TIMEOUT_IN_SECONDS,
        )
        try:
            resp.raise_for_status()
        except Exception:
            pass


    def run(self) -> None:
        console = self.console
        console.clear()
        console.print("[!] Epic Games Friends List Remover")

        # 1) Get a client token (for device auth creation)
        client_token = self.token_client_credentials()["access_token"]

        # 2) Create a device code and show the verification URL
        device = self.create_device_code(client_token)
        console.print("[>] Login Link:")
        console.print(f"[bold green]{device['verification_uri_complete']}")
        console.input("\n[*] Press Enter once you have logged in")

        # 3) Exchange for a *user* access token (bearer)
        try:
            user_auth = self.exchange_device_code_for_user_token(device["device_code"])
        except HTTPError:
            console.print("[red]User not logged in or device code expired.[/]")
            return

        self.account_id = user_auth["account_id"]
        self.user_bearer = user_auth["access_token"]
        user_display = user_auth.get("displayName", "<you>")

        console.print(f"[+] Logged in as ({user_display})")
        console.print()

        # 4) Fetch friends
        friends_summary = self.get_friends_summary()
        friends = friends_summary.get("friends", []) or []
        if not friends:
            console.print("[yellow]No friends found.[/]")
            self.kill_session()
            return

        # 5) Resolve display names in batches of 100
        account_ids = [f.get("accountId") for f in friends if f.get("accountId")]
        display_map = self.resolve_display_names(account_ids)

        # 6) Build rows for UI
        rows: List[Dict[str, str]] = []
        for f in friends:
            aid = f.get("accountId", "")
            rows.append(
                {
                    "accountId": aid,
                    "displayName": display_map.get(aid, "<unknown>"),
                    "mutual": str(f.get("mutual", 0)),
                    "created": f.get("created", ""),
                }
            )

        # Sort by display name for usability
        rows.sort(key=lambda r: (r["displayName"].lower(), r["accountId"]))

        # 7) Interactive selection UI
        console.print("[bold]Use the interface below to select friends to remove.[/]")
        ui = EpicFriendsUI(console)
        selected_ids = ui.select(rows, viewport_size=14)

        if not selected_ids:
            console.print("[yellow]No selection made or cancelled. Exiting without removing anyone.[/]")
            self.kill_session()
            return

        # Confirm removal
        confirm = Confirm.ask(f"[bold red]Remove[/] [cyan]{len(selected_ids)}[/] friend(s)?")
        if not confirm:
            console.print("[yellow]Cancelled. No changes made.[/]")
            self.kill_session()
            return

        # 8) Remove selected
        successes: List[str] = []
        failures: List[Tuple[str, str]] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Removing selected friends...", total=len(selected_ids))
            for fid in selected_ids:
                try:
                    self.remove_friend(fid)
                    successes.append(fid)
                except HTTPError as e:
                    status = str(getattr(e.response, "status_code", "HTTPError"))
                    failures.append((fid, status))
                except Exception as e:  # catch-all to keep the loop going
                    failures.append((fid, repr(e)))
                finally:
                    progress.update(task, advance=1)

        console.print()
        console.print(f"[green]Removed:[/] {len(successes)}")
        if failures:
            console.print(f"[red]Failed:[/] {len(failures)}")
            for fid, why in failures[:10]:
                console.print(f"  - {fid}: {why}")
            if len(failures) > 10:
                console.print(f"  ... and {len(failures) - 10} more")

        # 9) Kill session
        self.kill_session()
        console.print("[bold yellow]Session has been killed.[/]")

        console.print()
        console.print("[dim]Done.[/]")


def main() -> None:
    FriendsRemover().run()


if __name__ == "__main__":
    main()
