# AI-Intel-System

## 项目描述

AI-Intel-System 是一个智能情报收集和分析系统，能够自动从多个来源收集数据，包括博客、GitHub 趋势、研究论文、Twitter、视频等，并通过 AI 驱动的处理器进行去重、过滤、评分和趋势分析，最终生成每日报告。

## 功能特性

- **多源数据收集**：支持从博客、GitHub 趋势、研究 feeds、Twitter 和视频平台收集情报数据
- **智能处理**：包括数据去重、过滤、评分、信号标准化和趋势分析
- **AI 生成报告**：使用 LLM 客户端自动生成每日情报报告
- **灵活存储**：基于 JSON 的数据存储和状态管理
- **调度系统**：内置调度器支持定时任务执行
- **前端界面**：简单的 Web 界面用于查看报告
- **可扩展架构**：模块化设计，便于添加新的收集器和处理器

## 安装要求

- Python 3.8+
- pip

## 安装步骤

1. 克隆项目仓库：
   ```bash
   git clone <repository-url>
   cd AI-Intel-System
   ```

2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

3. 配置系统：
   编辑 `config.yaml` 文件，设置必要的 API 密钥和其他配置项。

## 使用方法

### 启动系统

运行主程序：
```bash
python main.py
```

### 启动前端

运行批处理文件启动网页：
```bash
启动网页.bat
```

### 日常更新

使用 PowerShell 脚本进行日常更新：
```powershell
.\scripts\daily_update.ps1
```

## 项目结构

- `collectors/` - 数据收集器模块
- `core/` - 核心系统组件（管道、注册表、调度器）
- `data/` - 数据存储文件
- `docs/` - 项目文档
- `frontend/` - 前端界面
- `generator/` - 报告生成器
- `models/` - 数据模型定义
- `processor/` - 数据处理器
- `scripts/` - 自动化脚本
- `storage/` - 存储模块
- `utils/` - 工具函数

## 配置

系统配置通过 `config.yaml` 文件进行管理。请根据需要修改以下配置项：

- API 密钥
- 数据源配置
- 处理参数
- 存储设置

## 贡献

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建功能分支
3. 提交更改
4. 发起 Pull Request

## 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。
