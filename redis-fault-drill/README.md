# Redis 5 集群故障演练工具

在 Windows 上双击 **start.cmd** 打开菜单，通过 SSH 操作 N150。打开菜单、查看状态不会注入故障。
使用 Python 3.9+、Windows OpenSSH；不需要安装第三方 Python 包。服务器需要 Python 3、Docker、systemd 和 root SSH 权限。

默认目标是 `192.168.2.126:7001–7006`，容器为 `n150-redis-7001` 至 `n150-redis-7006`。
工具读取服务器 `/opt/stacks/redis-cluster/.env` 中的密码，不把 Redis 密码下载到 Windows，也不写入命令行或工具日志。

## 两种故障

| 操作 | 应用看到的现象 | 实现 | 恢复 |
| --- | --- | --- | --- |
| 写入立即报错 `reject-writes` | SET/DEL 等写命令返回 `NOREPLICAS`；GET 等普通读取继续 | 临时将全部 6 个节点的 `min-replicas-to-write` 设为 6；必要时启用非零复制延迟阈值。集群只有 6 个节点，无法满足 6 个副本 | 恢复各节点演练前的参数；不执行 CONFIG REWRITE |
| 阻塞所有读写 `pause-io` | 已建立连接上的读写等待，达到客户端超时则报错；新连接的握手行为取决于 TCP 积压队列 | `docker pause` 暂停这 6 个容器，包含 Redis 执行、心跳和复制 | `docker unpause`；集群可能需要几秒重新收敛 |

Redis 5 没有 `CLIENT PAUSE WRITE` 和 `CLIENT UNPAUSE`。本工具选择容器暂停来支持**提前恢复读写**。
这不模拟“仅写入等待而读取正常”；也不会把立即报错描述成超时。
应用如果排队、重试，恢复后可能补执行之前的请求。请结合应用的超时、重试和幂等逻辑观察。

## Windows 命令行

在此目录执行：

```powershell
python .\redis_fault.py status
python .\redis_fault.py reject-writes --seconds 60
python .\redis_fault.py probe
python .\redis_fault.py resume
python .\redis_fault.py pause-io --seconds 30
python .\redis_fault.py --json status
```

默认持续 60 秒，允许 5–3600 秒。两个故障模式互斥，要切换模式先执行 `resume`。
`resume` 可重复运行，只恢复当前工具记录的演练；没有活动演练时不修改任何节点。
自定义目标可复制 `config.json` 为 `config.local.json`，再使用 `--config config.local.json`；两个配置文件都不应包含密码。

## 自动恢复与回退

- 注入前检查全部六个节点、版本、节点身份、集群成员和 16,384 个槽位。
- 先记录原值，再创建并确认服务器的 systemd 恢复定时器，最后才注入故障。定时器创建失败就不注入。
- Windows 工具退出或 SSH 断开不会取消已经安排的恢复。恢复失败时服务器服务每 3 秒重试。
- 部分节点执行失败时立即尝试恢复全部六个节点。某一节点不可达不会阻止其他节点恢复。
- 恢复时核对容器 ID 和原有参数；目标被替换或其他操作者改变参数时会报告冲突，避免覆盖新的配置。
- 定时器带独立演练 ID，过期的旧定时器不会解除新的演练。
- 定时器是 systemd transient timer：跨主机重启不保留。容器重启会解除进程暂停，未写入配置文件的参数也会还原；主机重启后请运行 `status` 和 `resume` 核对并结束旧演练记录。

服务器工具、原值记录及每次演练使用的恢复程序保存在 `/opt/stacks/redis-cluster/fault-drill/`。
密码只留在既有 `.env` 文件中。状态文件 `state.json` 不含密码。

## 验证与诊断

`probe` 对三个主节点分别使用**独立连接**发送 GET 和 DEL，观察返回值与耗时。
键使用随机 UUID 和正确分片的哈希槽，仅删除随机不存在的探测键，不插入数据，也不扫描业务键。
正常时读写均为 `ok`；拒写模式下读为 `ok`、写为 `NOREPLICAS`；暂停模式下两者均为 `timeout`。
身份验证也可能因容器暂停而超时，这同样说明该端点无法响应客户端。

服务器上也可运行：

```sh
python3 redis_fault.py --config /path/to/config.json status
python3 redis_fault.py --config /path/to/config.json reject-writes --seconds 60
python3 redis_fault.py --config /path/to/config.json resume
```

故障期间可在服务器检查恢复任务：

```sh
systemctl list-timers 'redis-fault-*'
journalctl -u 'redis-fault-*' --since '10 minutes ago' --no-pager
```

## 测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

集成测试需要指定 `REDIS_DRILL_TEST_CONFIG`，并强制要求目标为 `127.0.0.1` 且容器名以 `redis-drill-test-` 开头，避免对实际集群执行故障测试。
覆盖两种故障、手动恢复、自动恢复、非默认原值恢复、故障互斥、旧定时器隔离、恢复定时器创建失败及部分执行失败回退。

参考：[Redis 5 配置说明](https://raw.githubusercontent.com/redis/redis/5.0.14/redis.conf)、[Docker pause](https://docs.docker.com/reference/cli/docker/container/pause/)、[Redis CLIENT PAUSE](https://redis.io/docs/latest/commands/client-pause/)。
