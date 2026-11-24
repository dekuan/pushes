# Pushes for Git

一个以 **push** 为核心、支持一键暂存并提交全部改动的轻量 TUI，优先支持 macOS，也可在有 Python curses 的 Linux 终端使用。免费开源，MIT 许可证。无需 GitHub Desktop，不依赖 GitHub API，也适用于其他 Git 远端。

## 安装与启动

需要 Git、Python **3.9+**（含标准库 `curses`），无需 pip 包。macOS 不保证自带可用的 Python 3，可从 [Python 官网](https://www.python.org/downloads/macos/) 安装。Git 可通过 `xcode-select --install` 安装。

从当前克隆安装：

```sh
sh install.sh
```

安装到 `~/.local/bin/pushes`，无需 sudo；脚本会打印 PATH 和 zsh 补全配置，按输出加入 `~/.zshrc`。配置后重新打开终端，可在任意目录输入 `pushes`，并用 Tab 补全命令、选项和目录。支持 `PUSHES_BIN_DIR`、`PUSHES_COMPLETION_DIR` 自定义安装位置。

代码发布到 GitHub 的 `main` 后，可通过 URL 安装（当前本地修改尚未发布）：

```sh
curl -fsSL https://raw.githubusercontent.com/dekuan/pushes/main/install.sh | sh
```

也可直接运行：

```sh
python3 pushes.py
python3 pushes.py /path/to/projects
python3 pushes.py --fetch-interval 120
python3 pushes.py --fetch-interval 0 --ascii
python3 pushes.py --once
```

## 界面与操作

顶部显示名称、当前系统本地时间（每秒更新）、UTC 时区偏移，以及扫描目录。表格为 `Repo / Branch / Commits / Status / Details`；底部显示选中仓库的远端地址、历史提交数量、最新提交时间和摘要、上游及最近成功 fetch 时间。

| 键 | 功能 |
| --- | --- |
| ↑ / ↓ 或 K / J | 选择仓库或分支 |
| Enter | 对选中的仓库执行 `git push`；在分支列表中确认切换 |
| B | 打开本地和远端分支列表 |
| C | 底部输入 commit message，Enter 暂存并提交全部改动，Esc 取消 |
| Esc | 关闭分支列表 |
| G | 重新发现仓库，并请求刷新和 fetch |
| Q | 退出 |

状态图标：🧨 有未提交改动（含未跟踪文件）；🟡 有领先上游的提交；✓ 工作树干净且与上游一致；`!` 表示落后、分叉、无上游等需要注意的状态。脏状态优先显示图标，提交数量仍独立显示。终端 emoji 宽度异常时使用 `--ascii`（`*` / `+` / `v`）。

## Git 行为与边界

- 在仓库内运行时只显示该仓库（子目录也能识别所属仓库）；否则只扫描当前目录的一级子目录，不递归。支持 `.git` 文件形式的 worktree。
- `Commits` 是 `HEAD` 相对 `@{upstream}` 的领先数量，不是历史总量，也不是未提交文件数。没有可解析上游时显示 `?`；落后和分叉单独显示。历史总数为当前 HEAD 可达的提交数。
- 默认每 2 秒检查本地，每 60 秒执行 `git fetch --all --quiet`。后台任务不阻塞时钟和键盘；单仓库任务串行，最多四个仓库并行。网络结果只在 fetch 成功后更新，离线时仍显示本地状态和错误。
- Enter 执行原生 `git push`，遵循仓库已有的 remote、pushRemote、push refspec 和 push.default 配置；可能不止推当前分支，取决于你自己的 Git 配置。`Commits` 比较的是上游；若推送目标与上游不同，这个数量不代表目标端差异。无上游时不会擅自选择远端；Git 若未配置自动建立上游，会显示其错误。
- C 打开单行提交输入，支持中文、左右移动、Home/End、Backspace/Delete；输入期间 Q 等字母作为文本。输入区明确提示 Enter 将在选中仓库根目录执行 `git add .`，然后执行 `git commit -m`，包含新增、修改、删除的全部改动，遵守 `.gitignore`，不自动 push。按 C 仅打开输入，Esc 取消不修改暂存区。空消息不能提交；没有可提交改动或 Git hook 失败时保留消息以便修改重试。若暂存成功而提交失败，内容保留在暂存区。提交过程显示 `COMMITTING`，成功后更新提交数量和 Last 信息。
- 不执行 pull、merge、rebase、强推或自动解决冲突。脏仓库可以 push 已有提交。分支切换遇到脏工作树会拒绝，不自动 stash；远端分支通过建立本地跟踪分支切换，同名本地分支已存在时 Git 会拒绝，请选择已有本地分支。
- Git 使用现有 SSH agent / 凭据管理器；后台不允许终端密码提示。请先在普通终端完成 Git 认证。fetch 超时 30 秒，push 超时 120 秒；退出立即恢复终端，正在执行的 Git 任务会在完成或超时后结束进程。Git hooks 和凭据程序仍遵循本机配置。
- 界面适合至少 100 列，最小 64×16。长信息按可用宽度截断。Windows 原生终端暂不支持；可在 WSL 中使用。

卸载：删除安装路径中的 `pushes` 和补全目录中的 `_pushes`，并按需删除自行添加的 shell 配置。

## 开发验证

```sh
python3 -m unittest discover -s tests -v
python3 pushes.py --once
```

详细需求与实现取舍见 [docs/requirements.md](docs/requirements.md)。
