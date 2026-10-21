# 参考与实现取舍

项目内独立实现，未复制参考项目代码、角色或模型。

## 0.7.3 音乐调度参考（2026-10-21）

查阅 [VPet MainLogic.cs](https://github.com/LorisYounger/VPet/blob/main/VPet-Simulator.Core/Display/MainLogic.cs)：事件计时与显示调用分离，显示有开始和循环调用；其事件定时器为 15 秒，但不能把该值理解成动作固定切换间隔。查阅 [DesktopPet 动作配置](https://github.com/PhilippVn/DesktopPet#custom-animations)：按状态目录组织帧，并通过配置的状态转移和点击专用状态管理动作。也查看 Shijima-Qt 项目与发布说明，未复制其实现。

结合这些状态与播放分离的思路，本项目采用较长主动作段、完整循环结束后转移、短暂互动优先和独立小动作冷却。45/45、弱音乐托腮 80%、持续确认 6/4 秒、共享冷却 120 秒均为本项目按用户偏好制定的参数，不声称是上述项目的默认值或现成网易云/BPM 功能。

- [BongoCat](https://github.com/ayangweb/BongoCat)：参考输入驱动参数、模型与界面职责区分的方向。它使用 Live2D；本项目没有引入 Cubism，不把普通 PNG 宣称为 Live2D。
- [VPet Main.xaml.cs](https://github.com/LorisYounger/VPet/blob/main/VPet-Simulator.Core/Display/Main.xaml.cs)：查看互动检测及动作开始、循环、结束调用，参考状态组织和短暂互动后恢复，不假定其支持网易云。
- [Windows 媒体会话](https://learn.microsoft.com/zh-cn/uwp/api/windows.media.control.globalsystemmediatransportcontrolssession)：按目标会话实际能力读取信息和控制，不用标题推断正在播放。
- [Windows 进程回环示例](https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/)：评估了进程隔离捕获，当前未引入原生辅助程序，采用明确开启的系统回环并说明混音范围。
- [PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch)：使用 WASAPI 输出回环，不选择麦克风。
- [PyWinRT](https://github.com/pywinrt/pywinrt)：使用模块化 Windows.Media.Control 等绑定。

声音分析只计算能量和平滑起音，不提取会员音源或绕过加密。连续动画采用预乘透明通道的局部重采样，不是新增的手绘动作。依赖许可见各自发行包，角色素材来源与生成提示词保留在 `assets`。
