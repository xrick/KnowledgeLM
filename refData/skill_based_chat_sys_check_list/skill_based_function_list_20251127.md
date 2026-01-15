📚 Skill-Based-Doc-Chat 系统功能总览
🎯 一、用户交互层功能
1.1 Skill 主页面 (skill_main.html)
Skill 选择树
用途：从左侧边栏选择要查询的知识库
显示已加载的 Skills 及其文档数量
聊天界面
用途：与选定的 Skill 进行问答交互
支持流式对话展示
查询输入框
用途：输入自然语言问题
自动获焦和禁用状态管理
查询发送按钮
用途：提交查询并触发 RAG 检索-生成流程
包含加载动画反馈
加载动画 (Loading Spinner)
用途：查询处理中的可视化反馈
显示"正在进行搜索..."和"系统正在检索相关内容..."
聊天历史显示
用途：展示对话历史记录
支持 Markdown 格式渲染
相关来源显示
用途：展示 RAG 检索得到的源文档
显示相关度评分和文档位置
清除聊天按钮
用途：清除当前对话历史
1.2 Skill 配置页面 (skill_config.html)
统计卡片面板
用途：显示系统关键数据
包含：技能数、PDF 来源数、即时附件数、重建阈值
重建阈值配置
用途：动态设置即时附件积累到多少时触发重建
可编辑的数字输入 (1-50)
带有帮助提示
Skill 和 PDF 来源管理卡片
用途：CRUD 管理 Skills 和关联的 PDF 源
支持添加新 Skill
支持为 Skill 添加/删除 PDF 源
显示每个 PDF 的文件大小
即时附件区域（可折叠）
用途：管理临时上传的 PDF 待重建队列
显示附件列表及其所属 Skill
支持删除单个或批量清除
重建警告提示
用途：当即时附件达到阈值时提示用户
提供"立即重建"快速按钮
PDF 文件选择器模态框（Finder 风格）
用途：浏览和选择要添加的 PDF 文件
左侧：分类导航和文件夹树
右侧：文件列表（显示名称、路径、大小）
搜索功能按文件名过滤
分类快捷导航
重建日志模态框
用途：查看技能索引重建的过程日志
信息框说明重建日志内容
显示最近的重建日志行
刷新按钮获取最新日志
添加 Skill 模态框
用途：创建新的知识库技能
输入：技能名称、描述、分类
添加 PDF 源模态框
用途：为已有 Skill 添加 PDF 源
显示目标 Skill
PDF 路径选择和描述
1.3 File Mode 页面 (index.html)
返回按钮（新增）
用途：从 File Mode 返回 Skill 模式
位置：左侧边栏顶部
样式：紫色渐变按钮 + 返回箭头图标
新增来源按钮
用途：上传新的 PDF 文件
调试模式开关
用途：启用/禁用调试输出
资料来源列表
用途：显示已上传的 PDF 文件列表
聊天标签页
用途：针对单个 PDF 的查询交互
资料来源管理标签页
用途：管理上传的文件
⚙️ 二、后端 API 功能
2.1 Skill 管理 API (/api/v1/skills/*)
获取 Skills
GET / - 列出所有 Skills
GET /demo - 获取 demo 展示用的 Skills（带图标）
创建 Skill
POST /upload - 从文本内容创建新 Skill
用途：将文本数据转换为可检索的知识库
过程：文本分块 → 向量化 → 存储到 FAISS + SQLite
查询 Skill
POST /demo/query - 查询单个 Skill
用途：接收用户问题，返回 RAG 生成的答案
流程：向量检索 → 上下文组装 → LLM 生成 → 返回答案
POST /chat - 聊天端点（支持多个 Skills）
用途：同时查询多个 Skills
2.2 PDF 配置管理 API (/api/v1/skills/config/*)
获取配置
GET /config - 获取完整的 Skill 配置
返回：所有 Skills、PDF 来源、即时附件、重建阈值
GET /config/skills - 获取 Skills 列表和他们的 PDF 源
Skill 管理
POST /config/skills - 添加新 Skill
POST /config/skills/{skill_name}/sources - 为 Skill 添加 PDF 源
DELETE /config/skills/{skill_name}/sources - 删除 PDF 源
即时附件管理
GET /config/instant-attachments - 获取待重建的附件列表
POST /config/instant-attachments - 添加新的即时附件
DELETE /config/instant-attachments - 清除所有即时附件
重建阈值管理（新增）
PUT /config/rebuild-threshold - 更新重建触发阈值
用途：用户可动态调整何时自动触发重建
参数：新的阈值数值 (1-50)
返回：旧/新阈值、当前附件数、是否触发重建
PDF 浏览
GET /available-pdfs - 获取所有可用 PDF 文件列表
用途：为文件选择器提供目录树和文件列表
返回：层级结构树 + 扁平化文件列表 + 分类列表
2.3 重建管理 API (/api/v1/skills/*)
触发重建
POST /rebuild - 启动异步重建过程
用途：基于 JSON 配置重建所有 Skills 索引
模式：支持智能模式（仅重建受影响的 Skills）
支持：指定 Skill、清除模式、强制全量重建
查看重建状态
GET /rebuild/status - 获取最近的重建日志
用途：用户查看重建进度
返回：最后 20 行日志、修改时间、日志存在状态
🔍 三、核心 RAG 功能
3.1 向量检索系统
FAISS 索引存储
用途：存储 Skill 的向量数据
位置：/data/faiss_indices/skills/{skill_id}/
特点：每个 Skill 一个单独的 merged index
并行向量检索
用途：同时从多个 Skills 检索相关内容
优化：异步任务并行执行
相关度评分
用途：衡量检索结果与查询的匹配度
返回：分数用于排序和过滤
3.2 向量化和嵌入
嵌入模型选择
默认：BAAI/bge-m3
备选：sentence-transformers/all-MiniLM-L6-v2
维度：1024 (bge-m3) 或 384 (MiniLM)
3.3 文本分块系统
分块策略
Skill 级：1000 字符/块，200 字符重叠
用途：平衡语义完整性和检索精度
3.4 RAG 提示工程
上下文组装
用途：将检索结果转换为 LLM 输入
特点：清晰标注源文档、页码等元数据
多语言支持
中文、英文等多语言提示词
回答策略
优先引用文档内容
避免凭空编造信息
不在开头说"找不到资料"
🗃️ 四、数据管理功能
4.1 数据库系统
SQLite 元数据库
位置：./data/skill_metadata.db
用途：存储 Skill 元信息（名称、描述、分类、文档数）
JSON 配置文件
位置：./scripts/skill_data/skill_config.json
用途：定义 Skills 的 PDF 源、重建阈值等
支持：Skill 列表、即时附件队列、系统设置
4.2 文件管理
PDF 来源存储
位置：./refData/rawdata/ 及子目录
用途：存储所有知识库的 PDF 文件
日志记录
位置：./logs/rebuild_skills.log
用途：记录重建过程的详细日志
🤖 五、智能重建系统
5.1 SmartRebuildStrategy（智能策略）
重建范围判断
NONE：无附件，无需重建
TARGETED：有附件达到阈值，仅重建受影响的 Skills
ALL：强制全量重建
受影响 Skill 识别
用途：根据即时附件的归属 Skill，确定需要重建的目标
自动清理机制
用途：重建完成后自动清除已处理的附件
避免数据碎片化
5.2 后台重建任务
异步执行
用途：非阻塞的后台重建过程
防止长时间重建导致 API 超时
环境变量控制
SKILL_CONFIG_PATH：配置文件路径
SKILL_FILTER：指定 Skill 名称
FORCE_ALL：强制全量重建
SMART_REBUILD：是否使用智能策略
🎨 六、用户界面特性
6.1 设计系统
颜色变量系统
主色：#667eea (紫蓝)
辅色：#764ba2 (紫色)
成功：#10b981 (绿)
警告：#f59e0b (黄)
危险：#ef4444 (红)
6.2 交互反馈
加载动画
旋转 spinner
背景模糊效果
文字提示
模态框
半透明背景
支持快速关闭
表格和列表
悬停高亮
滚动优化
📊 七、监控和日志功能
重建日志文件
位置：./logs/rebuild_skills.log
内容：每个重建过程的完整日志
访问方式：通过 Rebuild Logs 模态框查看
API 错误日志
用途：记录 API 调用的错误信息
便于故障排查
配置变更日志
用途：记录 Skill 配置的修改历史
last_updated 字段跟踪最后更新时间
📋 八、配置和设置
8.1 系统配置 (app/core/config.py)
LLM 参数：模型、温度、最大 token 数
嵌入配置：模型选择、维度、设备
向量数据库：Milvus 或 FAISS 选择
文本分块：策略、块大小、重叠
8.2 Skill 配置 (skill_config.json)
Skills 定义：名称、描述、分类、启用状态
PDF 源：相对路径、启用状态、描述
即时附件：待重建的 PDF 队列
重建阈值：触发自动重建的附件数量
文本分块参数：Skill 级的分块配置
📝 总结
Skill-Based-Doc-Chat 系统包含 8 大功能模块、30+ 个具体功能，涵盖：
✅ 用户交互（6 个前端页面/区域）
✅ 后端 API（18+ 个端点）
✅ 核心 RAG（4 个子系统）
✅ 数据管理（2 个存储系统）
✅ 智能重建（3 个决策机制）
✅ UI 特性（3 个设计方面）
✅ 监控日志（3 个日志类型）
✅ 配置管理（2 个配置层级）
核心优势：
🎯 多 Skill 并行查询
⚡ 智能增量重建（避免全量重建）
🔄 异步后台处理（无阻塞）
📁 Finder 风格文件浏览
🎚️ 动态阈值配置
📊 详细重建日志