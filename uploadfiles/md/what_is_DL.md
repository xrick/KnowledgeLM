深度學習（Deep Learning）是機器學習的一個分支，核心做法是用「多層」人工神經網路從大量資料中自動學出特徵與規律，進而完成分類、預測、生成等任務。 「深」指的是網路中有多個層（通常至少三層以上），讓模型能把原始輸入逐層轉換成更抽象的表示。 [ibm](https://www.ibm.com/think/topics/deep-learning)

## 它怎麼運作
深度學習模型一般由輸入層、數個隱藏層、輸出層組成，資料會在層與層之間傳遞，每一層透過權重與非線性轉換去萃取不同層次的特徵。 訓練時會根據預測誤差調整權重（學習），讓模型對新資料也能做出更準確的判斷。 [geeksforgeeks](https://www.geeksforgeeks.org/deep-learning/introduction-deep-learning/)

## 和傳統機器學習差在哪
傳統機器學習常需要人手設計特徵（feature engineering），例如先想好要量測哪些訊號或統計量再丟給模型。 深度學習更擅長直接從影像、文字、語音等「非結構化資料」中自動學出有效表示，降低手工特徵設計的需求。 [aws.amazon](https://aws.amazon.com/what-is/deep-learning/)

## 常見應用
深度學習廣泛用在影像辨識、自然語言處理與語音辨識等問題上，因為它能在大量資料下學到複雜模式。 例如影像模型可能在前幾層學到邊緣與形狀，後面逐步組合成物體或人臉等高階概念。 [en.wikipedia](https://en.wikipedia.org/wiki/Deep_learning)

## 典型模型例子
在視覺領域常見 CNN（卷積神經網路），在序列資料與語言上則常見 Transformer（也是近年大型語言模型的核心結構之一）。 [geeksforgeeks](https://www.geeksforgeeks.org/deep-learning/deep-learning-101/)

你想要的是「給初學者的白話版」介紹，還是「偏工程/數學（反向傳播、損失函數、優化器）」的入門？