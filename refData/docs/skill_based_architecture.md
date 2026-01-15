<!-- refData/docs/skill_based_architecture.md -->

我們現在碰到一個很麻煩的問題：主管要求架構重整，以Skill-Based Architecture
1. Skill的定義：
	1.1. 一個skill是多個(經由設定可以是20個，也可以是100個)內容高相關的pdf files的Embeddings。
	1.2. 目前在main page，一次只有一個skill被選擇。
	1.3. 當一個skill被選擇後，使用都可以對這skill進行詢問。你可以看成對組成這個skill的所有文件的embedding進行查詢。
2. 新增一個skill，在./data/ 目錄下新增一個檔案夾，並且以skill的名稱為檔案夾用來儲存與這個組成這個skill的pdf files embeddings。
3. sqlite必須新增相關的tables或db來完成這功能。
4. 從以上的描述，總結就是使用者要把內容相關或類似的pdf files組成一個group，也就是skill.
5. 新建的DB請把docai.db中的users table拷貝進來。
6. separate the new architecture
請參考以下的images.
- skill-based architecture: refData/design/skill-based architecture.jpeg
- faiss儲存的結構：refData/design/faiss_save_architecture.jpeg
- mainpage.html: refData/design/main_page_1.jpeg
- 新增新skill的popup modal window: refData/design/skills管理.jpg
please step by step to read, analyze and understand the new "BIG" functionalities like an experienced and talent RAG expert