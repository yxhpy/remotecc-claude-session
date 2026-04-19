# remotecc-claude-session

一个自包含的 Codex Skill，用来通过 SSH 在远程机器上运行 Claude Code，并用可恢复的 session 管理整条链路。

它解决的是这类场景：

1. 把本地项目同步到远程服务器。
2. 在远程 `tmux` 里启动 Claude Code。
3. 从 Codex 或命令行向远程 Claude 发送指令。
4. 把远程修改后的文件拉回本地。
5. 把 session 状态保存在本地，方便恢复、探活和关闭。

这个仓库同时包含两部分：

- 一个可被 Codex 调用的 skill：`remotecc-claude-session`
- 一个可直接运行的 CLI：`scripts/remotecc.py`

## 它适合谁

适合这些情况：

- 你希望让 Claude Code 跑在远程 Linux 机器上
- 远程机器的网络、环境或服务访问能力更合适
- 你不想靠手动开一堆 `ssh` 标签页来维持会话
- 你需要给上层 skill 或自动化提供稳定的命令行接口

## 它提供什么

- 基于 SSH + `rsync` 的工作目录同步
- 基于 `tmux` 的远程 Claude 会话管理
- 本地 session registry：`~/.remotecc/sessions.json`
- 密码登录的 bootstrap 能力，底层使用 SSH control master
- `ready --json` 非交互探活接口，方便 skill 判断能否继续执行
- 明确的模型路由：`haiku`、`sonnet`、`opus`、`opusplan`

## 安装方式

### 方式一：直接 clone

把仓库放到 Codex skills 目录下：

```bash
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/skills/remotecc-claude-session
```

如果你使用 `CODEX_HOME`，则放到：

```bash
${CODEX_HOME}/skills/remotecc-claude-session
```

安装后，Codex 就可以通过下面这个名字调用它：

```text
$remotecc-claude-session
```

### 方式二：通过 skill-installer 安装

如果你已经在用 Codex 自带的 `skill-installer`，可以直接执行：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo yxhpy/remotecc-claude-session --path . --name remotecc-claude-session --method git
```

注意：

- `--path .` 不能省，因为这个仓库根目录本身就是 skill 根目录
- `--method git` 是更稳的方式，能避开某些机器上 Python HTTPS 下载的证书问题
- 安装完成后要重启 Codex，新的 skill 才会被发现

## 依赖要求

本地机器需要：

- `ssh`
- `rsync`
- Python 3.10+

远程机器需要：

- `bash`
- `tmux`
- `rsync`
- 已安装并已登录的 `claude` CLI

## 在 Codex 里怎么调用

示例：

```text
Use $remotecc-claude-session to create a remote Claude session on root@example.com for /Users/me/project, use the standard profile, start it, and report whether it is ready for non-interactive use.
```

这个 skill 内部调用的是仓库自带的 CLI：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py --help
```

## 快速开始

### 1. 创建 session

默认日常编码模式：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard
```

如果首轮 bootstrap 需要输 SSH 密码，或者本地私钥有 passphrase：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard --password-auth
```

### 2. 探测 session 是否可被 skill 非交互使用

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py ready demo --json
```

如果 `ready` 不是 `true`，就不要假设上层 skill 可以继续 unattended 运行。

### 3. 启动远程 Claude Code

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo
```

### 4. 发送一条指令

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py send demo --text "Inspect the repo and fix the failing test."
```

### 5. 把远程改动拉回本地

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py pull demo
```

### 6. 关闭 session

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py close demo --drop-remote
```

## Session 规则

当 Claude Code 正在远程运行时，应该把远程工作目录视为当前写入端。

这几个命令的职责分别是：

- `create`：初始化远程工作目录，做首轮同步，并写入本地 session
- `start`：在远程 `tmux` 中启动 Claude Code
- `send`：向远程 Claude session 发送任务
- `pull`：把远程改动拉回本地
- `close`：关闭 session，并可选清理远程目录和 `tmux`

`closed` 状态的 session 只是历史记录，不应该继续对它 `send`、`attach` 或 `chat`。

## 认证模型

推荐两种模式：

- SSH key：适合真正的 unattended 使用
- `--password-auth`：只适合 bootstrap 阶段，由人手动输一次密码或 passphrase

`--password-auth` 不会存储密码。它会建立一个 session 级别的 SSH control master，让后续的 `ssh` 和 `rsync` 复用同一条连接。

所以给上层 skill 的约束应该是：

- 人类先完成 bootstrap
- skill 只有在 `ready --json` 通过后才继续执行

如果 control master 过期，可以重新连接：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py connect demo
```

## Claude CLI 首次运行的交互

远程机器第一次跑 Claude Code 时，可能仍然会被 Claude 自己的交互拦住，例如：

- workspace trust
- edit approval

这不是 SSH 层的问题。通常做法是 bootstrap 时手动处理一次。

如果你明确接受这个风险，也可以在创建 session 时传入更宽松的命令：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --model opus --claude-command "claude --dangerously-skip-permissions"
```

## 模型选择

先让 CLI 输出机器可读的模型信息：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py models --json
```

默认 profile 映射：

- `simple` -> `haiku`
- `standard` -> `sonnet`
- `complex` -> `opus`
- `plan` -> `opusplan`
- `long` -> `sonnet[1m]`

建议这样用：

- `haiku` 或 `hk`：列目录、grep、摘要、微小低风险改动
- `sonnet`：默认日常编码、普通实现、常规 bugfix
- `opus`：架构调整、高风险迁移、疑难排查、深度 review
- `opusplan`：先追求计划质量，再进入执行

你可以在创建时指定模型，也可以后续切换：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile complex
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py set-model demo --model opus
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo --model opus --restart
```

## 主要命令

CLI 当前支持：

- `models`
- `create`
- `list`
- `status`
- `ready`
- `connect`
- `set-model`
- `push`
- `pull`
- `start`
- `send`
- `capture`
- `attach`
- `close`
- `chat`

更具体的命令组合见 [references/command-cookbook.md](./references/command-cookbook.md)。

## 最小闭环

下面是一条最小可运行闭环：

```bash
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py create demo user@host --local-dir /abs/project --profile standard --password-auth
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py ready demo --json
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py start demo
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py send demo --text "Create a file named smoke.txt containing OK."
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py pull demo --force
python3 ~/.codex/skills/remotecc-claude-session/scripts/remotecc.py close demo --drop-remote
```

## 边界与假设

- 这是一个 MVP 级的 session 管理层，不是分布式文件系统
- 推荐路线是：同步进去，远程运行，同步回来
- 密码登录只是 bootstrap 手段，不是长期 unattended 架构
- 如果本地和远程同时改同一批文件，冲突合并由你自己处理

## 仓库结构

- [SKILL.md](./SKILL.md)：给 Codex 的 skill 说明
- [scripts/remotecc.py](./scripts/remotecc.py)：自带 CLI 入口
- [references/command-cookbook.md](./references/command-cookbook.md)：命令示例和常见问题

## 状态存储

本地 session 状态存储在：

```text
~/.remotecc/sessions.json
```

## 相关文件

- [README.md](./README.md)
- [SKILL.md](./SKILL.md)
- [references/command-cookbook.md](./references/command-cookbook.md)
