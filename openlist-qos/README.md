# OpenList 自适应低优先级策略

当前拓扑：

- OpenWrt：`192.168.2.1`
- OpenList 服务器：`192.168.2.200`
- OpenList 专用流量身份：`192.168.2.210`

策略行为：

- 其他设备流量超过约 2 Mbit/s 并持续 4 秒时，按其实际流量动态降低 OpenList 上限。
- 线路繁忙时，OpenList 最低仍保留约 512 Kbit/s。
- 其他设备流量降到约 1.2 Mbit/s 以下并持续 6 秒后，OpenList 自动恢复不限速。

路由器控制命令：

```sh
/usr/sbin/openlist-qos status
/usr/sbin/openlist-qos disable
/usr/sbin/openlist-qos enable
/usr/sbin/openlist-qos uninstall
```

`disable` 会立即移除限速规则，但保留文件，之后可用 `enable` 恢复。

服务器端状态与完整卸载：

```sh
/usr/local/sbin/openlist-qos-source status
/usr/local/sbin/openlist-qos-source uninstall
```

若只想临时取消策略，仅需在路由器执行 `disable`；服务器保留专用地址不会产生限速。

主要参数位于路由器 `/etc/config/openlist-qos`：

- `capacity_kbit`：估算的可用下行带宽。
- `minimum_kbit`：竞争激烈时 OpenList 的最低保留带宽。
- `trigger_kbit`：触发让路的其他设备流量阈值。
- `release_kbit`：解除让路的其他设备流量阈值。
- `trigger_seconds`：超过触发阈值后需要持续的时间。
- `reserve_kbit`：为其他设备额外预留的带宽。
- `release_seconds`：低于解除阈值后恢复不限速的等待时间。
