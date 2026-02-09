/sc:design  --focus quality --c7 --seq --serena
- 基於此分析設計一個完整的 DB 初始化 + 資料表建立 + 資料遷移方案 + 程式碼更動(請用表格表示，包括原本的sql statement與意義，及修改後的sql statement)
- "skill"前綴代表的是一項技能。
- "doc"表示某項skill所擁有的文件的id的前綴
- skill_metadata table中的skill_id目前是表示一份文件的id，必須更正回doc_id
- 