"""Device-owned diary blocks and explicit fast-forward synchronization."""
from __future__ import annotations

from datetime import date
import os
from pathlib import Path
import re
import subprocess
import tempfile

ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
MARK = re.compile(rb"<!-- daily-work-report(?::([a-z0-9][a-z0-9-]{0,63}))?:(start|end) -->")


def settings(cfg):
    device = cfg.get('device_id')
    if not isinstance(device, str) or not ID.fullmatch(device):
        raise ValueError('device_id 必须为 1—64 位小写字母、数字或连字符')
    name = cfg.get('device_name', device)
    if not isinstance(name, str) or not name.strip() or any(c in name for c in '\r\n<>#'):
        raise ValueError('device_name 必须为单行纯文本')
    legacy = cfg.get('legacy_device_id')
    if legacy is not None and (not isinstance(legacy, str) or not ID.fullmatch(legacy)):
        raise ValueError('legacy_device_id 格式无效')
    return device, name.strip(), legacy


def no_links(path):
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('日记路径不得包含符号链接或 junction')


def merge_blocks(old: bytes, block: bytes, device: str, legacy: str | None) -> bytes:
    matches = list(MARK.finditer(old))
    # Reject malformed markers as well as duplicated/nested/unpaired blocks.
    if old.count(b'<!-- daily-work-report') != len(matches):
        raise ValueError('日记自动区块标记损坏')
    spans, opened = {}, None
    for match in matches:
        if (match.start() and old[match.start()-1:match.start()] != b'\n') or old[match.end():match.end()+1] not in (b'', b'\n', b'\r'):
            raise ValueError('自动区块标记必须独占一行')
        owner = match[1].decode() if match[1] else None
        if match[2] == b'start':
            if opened is not None or owner in spans:
                raise ValueError('日记自动区块重复或嵌套')
            opened = (owner, match.start())
        else:
            if opened is None or opened[0] != owner:
                raise ValueError('日记自动区块标记不配对')
            spans[owner] = (opened[1], match.end())
            opened = None
    if opened is not None:
        raise ValueError('日记自动区块标记不完整')
    owner = device
    if None in spans:
        if legacy is None:
            raise ValueError('旧自动区块归属未知：请明确配置 legacy_device_id')
        if legacy in spans:
            raise ValueError('旧区块与所属设备区块同时存在，请人工核对')
        if legacy == device:
            owner = None
    if owner in spans:
        a, b = spans[owner]
        return old[:a] + block + old[b:]
    separator = b'' if not old else b'\n' if old.endswith(b'\n') else b'\n\n'
    return old + separator + block + b'\n'


def save_diary(cfg, packet, draft):
    # Caller has already saved and validated the standard report in a private temp dir.
    from daily_report import NOTE, prose
    device, name, legacy = settings(cfg)
    name = prose(name, '设备名称')
    day = date.fromisoformat(packet['report_date'])
    path = Path(cfg['output_dir']) / str(day.year) / str(day.month) / f'{day.day:02d}.md'
    no_links(path)
    original = path.read_bytes() if path.exists() else None
    lines = [f'<!-- daily-work-report:{device}:start -->', f'# {name}', '']
    for heading, states in [('今日完成', {'completed'}), ('进行中与问题', {'attempt', 'blocked', 'discussion'})]:
        items = [i for i in draft['items'] if i['state'] in states]
        if not items:
            continue
        lines += [f'## {heading}', '']
        for project in dict.fromkeys(i['project'].strip() for i in items):
            lines += [f'### {project}', '']
            for index, item in enumerate([i for i in items if i['project'].strip() == project], 1):
                text = f"{index}. {item['text'].strip()}"
                if 'problem' in item:
                    text += f" 问题：{item['problem'].strip()} 处理与验证：{item['resolution'].strip()}"
                lines += [text, '']
    lines += ['## 知识总结', '', draft['reflection']['text'].strip(), '']
    if packet['partial']:
        lines += [NOTE, '']
    lines += [f'<!-- daily-work-report:{device}:end -->']
    block = '\n'.join(lines).encode('utf-8')
    merge_blocks(block, b'', device, legacy)  # Reject markers injected through draft text.
    content = merge_blocks(original or b'', block, device, legacy)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.daily-report-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        no_links(path)
        if (path.read_bytes() if path.exists() else None) != original:
            raise ValueError('日记在保存期间被修改，已停止覆盖')
        os.replace(temporary, path)
        if path.read_bytes() != content:
            raise ValueError('日记回读验证失败')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {'status': 'saved', 'path': str(path), 'device_id': device}


def sync_repository(repo: Path, remote_url: str, branch: str = 'main'):
    """Explicit opt-in only. Never stash, reset, rebase, force or resolve conflicts."""
    repo = repo.expanduser().absolute()

    def git(*args):
        try:
            result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True,
                                    text=True, encoding='utf-8', timeout=120)
        except subprocess.TimeoutExpired:
            raise ValueError('Git 同步超时；请核对仓库状态后重试') from None
        if result.returncode:
            # Git errors can echo credential-bearing URLs or helper output.
            raise ValueError(f'Git {args[0]} 失败；未自动解决，请在本机核对')
        return result.stdout.strip()

    if Path(git('rev-parse', '--show-toplevel')).resolve() != repo.resolve():
        raise ValueError('必须指定 Git 仓库根目录')
    if git('branch', '--show-current') != branch:
        raise ValueError('当前分支与指定分支不一致')
    if git('remote', 'get-url', 'origin') != remote_url or git('remote', 'get-url', '--push', 'origin') != remote_url:
        raise ValueError('origin 地址与授权地址不一致')
    for state in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        marker = Path(git('rev-parse', '--git-path', state))
        if not marker.is_absolute():
            marker = repo / marker
        if marker.exists():
            raise ValueError('仓库存在未结束的合并、变基或拣选')
    if git('status', '--porcelain') or git('ls-files', '-u'):
        raise ValueError('仓库有未提交修改或冲突，请先处理后再生成日记')
    git('fetch', 'origin', branch)
    ahead, behind = map(int, git('rev-list', '--left-right', '--count', 'HEAD...FETCH_HEAD').split())
    if ahead and behind:
        raise ValueError('本地与远程历史分叉，停止同步')
    git('pull', '--ff-only', 'origin', branch)
    return {'status': 'synced', 'head': git('rev-parse', 'HEAD')}
