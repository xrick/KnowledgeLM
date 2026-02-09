我如何在修改程式前，在claude code 設定roll-back點

你在修改程式前要「設定 roll-back 點」，在 Claude Code 最直接的方法是用內建的 **checkpoint / rewind**（同一個 session 內可回到先前狀態），更保險則是用 Git（可跨 session、可長期保存）。 [code.claude](https://code.claude.com/docs/en/checkpointing)

## 方法 1：用 Claude Code 內建 Rewind（最快）
Claude Code 會在每次要改檔前先對檔案做快照，因此可在 session 內回復檔案變更。 [code.claude](https://code.claude.com/docs/en/how-claude-code-works)
操作方式：快速按 `Esc` 兩次（`Esc` + `Esc`），或輸入 `/rewind` 開啟回溯選單。 [code.claude](https://code.claude.com/docs/en/checkpointing)
在回溯選單中你可以選擇只回復程式碼（Code only）、只回復對話（Conversation only）、或兩者一起回復（Both）。 [code.claude](https://code.claude.com/docs/en/checkpointing)

## 方法 2：用 Git 建立「真正的 rollback 點」（最穩）
Git 能把狀態固定成一個可被回到的節點，且不受 Claude Code session 限制；這常被用作長期的 checkpoint。 [m](https://m.academy/lessons/use-git-persistent-version-control-tracking-claude-code/)
常見做法是在要讓 Claude 大改之前先建一個 commit 或 stash，例如用 stash 做「暫存還原點」會很乾淨、不會污染 commit 歷史（適合實驗）。 [github](https://github.com/anthropics/claude-code/issues/6001)

## 什麼時候用哪個
- 只是在同一輪 Claude Code 對話裡試改幾個檔：用 `/rewind` 最快。 [code.claude](https://code.claude.com/docs/en/checkpointing)
- 你要做大重構、可能跨多次 session、或需要可追溯的歷史：用 Git checkpoint 更可靠。 [m](https://m.academy/lessons/use-git-persistent-version-control-tracking-claude-code/)

你現在的環境是「Claude Code（獨立）」、「Cursor 內跑 Claude Code」，還是「VS Code」？你偏好用 Git commit 當 checkpoint，還是 stash 當 checkpoint？