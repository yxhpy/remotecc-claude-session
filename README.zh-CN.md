# remotecc

`remotecc` 是一个最小可用的远程 Claude Code session 管理器，同时当前仓库根目录本身也是 Codex skill 根目录。

现在这份仓库就是唯一维护入口：

- Python 源码在 `src/remotecc`
- Skill 入口在仓库根目录的 `SKILL.md`
- 仓库根目录启动脚本是 `scripts/remotecc.py`

不再需要维护另一份独立镜像仓库。

## 它做什么

`remotecc` 解决的是这条链路：

1. 用 `rsync` 把本地项目同步到远程机器
2. 在远程 `tmux` 里启动 Claude Code
3. 从 Codex 或命令行向远程 Claude 发送指令
4. 把远程修改后的文件拉回本地
5. 在本地保存 session 状态，方便探活、恢复和关闭

当前 MVP 故意采用 `rsync + ssh + tmux`，不做 SSHFS 一类的远程挂载。

## 为什么这样设计

第一版更看重 session 稳定性，而不是“像本地盘一样挂载远程目录”：

- 断线重连语义更清晰
- 延迟和 watcher 行为更容易控制
- 远程单写者模型更安全

## 仓库结构

- [SKILL.md](./SKILL.md)：给 Codex 的 skill 说明
- [agents/openai.yaml](./agents/openai.yaml)：skill 元数据
- [scripts/remotecc.py](./scripts/remotecc.py)：从仓库根目录直接运行
- [references/command-cookbook.md](./references/command-cookbook.md)：命令示例
- [src/remotecc](./src/remotecc)：实际 Python 实现

## 依赖

本地：

- `ssh`
- `rsync`
- Python 3.10+

远程：

- `bash`
- `tmux`
- `rsync`
- 已安装并登录的 `claude` CLI

本地 `rsync` 参数做了保守兼容，能适配 macOS 自带的旧版本实现。

## 本地开发

在当前仓库根目录安装 editable 包：

```bash
cd /path/to/remotecc
python3 -m pip install -e .
```

或者不安装，直接从仓库根目录运行：

```bash
python3 scripts/remotecc.py --help
```

## 作为 Codex Skill 使用

当前仓库根目录就是 skill 根目录。安装后可通过下面这个名字触发：

```text
$remotecc-claude-session
```

示例：

```text
Use $remotecc-claude-session to create a remote Claude session on root@example.com for /Users/me/project, use the standard profile, start it, and report whether it is ready for non-interactive use.
```

## 安装成 Skill

### 方式一：手动 clone

```bash
git clone https://github.com/yxhpy/remotecc-claude-session.git ~/.codex/skills/remotecc-claude-session
```

### 方式二：用 `skill-installer`

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo yxhpy/remotecc-claude-session --path . --name remotecc-claude-session --method git
```

注意：

- `--path .` 不能省，因为仓库根目录本身就是 skill 根目录
- `--method git` 能绕过某些机器上的 Python HTTPS 证书问题
- 安装完成后需要重启 Codex

## 快速开始

从当前仓库根目录创建 session：

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard
```

如果 bootstrap 阶段需要输密码或私钥口令：

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard --password-auth
```

探测 session 是否可供 skill 非交互继续执行：

```bash
python3 scripts/remotecc.py ready demo --json
```

启动远程 Claude Code：

```bash
python3 scripts/remotecc.py start demo
```

发送一条任务：

```bash
python3 scripts/remotecc.py send demo --text "Inspect this repo and summarize the entrypoint."
```

把远程改动拉回本地：

```bash
python3 scripts/remotecc.py pull demo
```

关闭 session：

```bash
python3 scripts/remotecc.py close demo --drop-remote
```

## Session 模型

每个 session 保存这些信息：

- 本地工作目录
- SSH 目标
- 远程工作目录
- 远程 `tmux` session 名称
- Claude 启动命令
- 模型 profile 和模型别名
- 生命周期时间戳

本地状态保存在：

```text
~/.remotecc/sessions.json
```

当 Claude Code 正在远程运行时，应把远程目录视为当前写入端。

推荐顺序：

1. `create`
2. `ready --json`
3. `start`
4. `send` 或 `chat`
5. `pull`
6. `close`

## 认证模式

推荐两种模式：

- SSH key：适合真正的 unattended 使用
- `--password-auth`：仅适合由人类完成首轮 bootstrap

`--password-auth` 不会存储密码，而是建立一个 session 级别的 SSH control master，后续 `ssh` 和 `rsync` 都复用它。

如果 control socket 过期：

```bash
python3 scripts/remotecc.py connect demo
```

对上层 skill 来说，规则就是：

- 人类可以做 bootstrap
- skill 只有在 `ready --json` 返回可用时才继续

## Claude 首次运行交互

远程第一次跑 Claude Code 时，仍然可能被 Claude 本身的交互卡住，例如：

- workspace trust
- edit approval

这不是 SSH 层问题。通常做法是 bootstrap 时手动处理一次。

如果你明确接受更宽松的权限模式，也可以传：

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --model opus --claude-command "claude --dangerously-skip-permissions"
```

## 模型选择

先获取机器可读的模型路由：

```bash
python3 scripts/remotecc.py models --json
```

默认 profile 映射：

- `simple` -> `haiku`
- `standard` -> `sonnet`
- `complex` -> `opus`
- `plan` -> `opusplan`
- `long` -> `sonnet[1m]`

建议用法：

- `haiku` 或 `hk`：列目录、grep、摘要、微小低风险改动
- `sonnet`：日常编码、普通实现、常规 bugfix
- `opus`：架构调整、高风险迁移、疑难排查、深度 review
- `opusplan`：先追求高质量规划，再进入执行

示例：

```bash
python3 scripts/remotecc.py models --json
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard
python3 scripts/remotecc.py start demo --model opus
python3 scripts/remotecc.py set-model demo --profile complex
python3 scripts/remotecc.py send demo --profile simple --text "Summarize this folder."
```

## 最小闭环

```bash
python3 scripts/remotecc.py create demo user@host --local-dir . --profile standard --password-auth
python3 scripts/remotecc.py ready demo --json
python3 scripts/remotecc.py start demo
python3 scripts/remotecc.py send demo --text "Create a file named smoke.txt containing OK."
python3 scripts/remotecc.py pull demo --force
python3 scripts/remotecc.py close demo --drop-remote
```

## 当前边界

- 不做实时远程挂载
- 不做自动冲突合并
- 不做远程进程沙箱
- 当前只支持基于 tmux pane 的输出抓取

## 相关文档

- [README.md](./README.md)
- [SKILL.md](./SKILL.md)
- [references/command-cookbook.md](./references/command-cookbook.md)
