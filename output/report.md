# AT 工程日志归因报告

## 任务概览
- **Job ID**: job-20260412-001
- **Build**: build-5823
- **执行时间**: 2026-04-12T08:30:00Z
- **主机**: test-runner-01
- **总计**: 156 | **通过**: 142 | **失败**: 8

## 失败用例分析

| 用例 | 类型 | 根因 | 置信度 |
|------|------|------|--------|
| virt_testsuite.guest_test.memory_hotplug | libvirt_error | 2026-04-12 08:41:23.678+08:00 12345: error: Domain | high |
| virt_testsuite.guest_test.nested_kvm | timeout | 2026-04-12 08:55:00.000+08:00 54321: error: Migrat | high |
| virt_testsuite.storage_test.qcow2_snapshot | qemu_crash | 2026-04-12 09:00:15.123+08:00 [qemu] error: qcow2_ | high |
| virt_testsuite.network_test.bridge_mtu | memory_issue | [1234567.890] oom-killer: gfp_mask=0x1400c0(GFP_KE | high |
| virt_testsuite.guest_test.virsh_console | kernel_panic | 2026-04-12 09:10:15.000+08:00 kernel: [2345678.123 | high |
| virt_testsuite.guest_test.live_migration | environment_issue | 2026-04-12 09:15:30.000+08:00 kernel: [3456789.123 | high |
| virt_testsuite.storage_test.iscsi_pool | infrastructure_issue | 2026-04-12 09:20:03.000+08:00 iscsiadm: Could not  | high |

## 建议

### 按类型统计
- **libvirt_error**: 1 个
- **timeout**: 1 个
- **qemu_crash**: 1 个
- **memory_issue**: 1 个
- **kernel_panic**: 1 个
- **environment_issue**: 1 个
- **infrastructure_issue**: 1 个

---
*由 AutoDectections Agent 自动生成 - 2026-04-12 19:37:58*
