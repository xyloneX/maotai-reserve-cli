"""CLI 品牌与图标（终端 ASCII）。"""

APP_NAME = "茅台抢单软件"
APP_NAME_EN = "MaoTai Grab"
APP_TAGLINE = "i茅台智能预约 · 个人自用"

# 终端内「图标」+ 酒樽 ASCII
LOGO = r"""
[bold red]    ████╗   ████╗[/]  [bold yellow]🍶[/]
[bold red]   ███╔╝   ╚███║[/]
[bold red]  ███╔╝  [white]i茅台[/][bold red]  ╚███╗[/]
[bold red] ███╔╝[/] [dim]━━━━━━━[/] [bold red]╚███╗[/]
[bold red]███╔╝[/]  [bold white]预约助手[/]  [bold red]╚███╗[/]
[bold red]╚███╗[/]               [bold red]███╔╝[/]
[bold red] ╚███╗[/]             [bold red]███╔╝[/]
[bold red]  ╚████╗[/] [bold yellow]茅台[/][bold red] ████╔╝[/]
[bold red]   ╚══███╗███████╔╝[/]
[bold red]      ╚═════╝╚════╝[/]
"""

SUBTITLE = (
    "[dim]官方 App 使用[/] [cyan]手机号 + 短信验证码[/] [dim]登录（非网页密码）[/]\n"
    "[dim]预约 ≠ 中签 · 中签后请在 i茅台 App 内支付[/]"
)


def set_terminal_title(title: str = APP_NAME) -> None:
    import sys

    if sys.platform == "darwin":
        sys.stdout.write(f"\033]0;{title}\007")
        sys.stdout.flush()
