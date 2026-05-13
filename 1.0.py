import jieba
import numpy as np
from gensim.models import Word2Vec

# 语料
sentences = [
    ["我", "爱", "自然语言处理"],
    ["机器", "学习", "是", "人工智能", "的", "分支"],
    ["词向量", "可以", "表示", "词语", "的", "语义"],
    ["猫", "狗", "狐狸", "都是", "动物"],
    ["狐狸", "很", "聪明"],
    ["狗", "会", "汪汪叫"],
    ["猫", "会", "喵喵叫"]
]

test_sent = "狐狸和狗都是聪明的动物"

# ===================== Word2Vec =====================
print("======= Word2Vec 结果 =======")
w2v_model = Word2Vec(sentences, vector_size=300, window=5, min_count=1)
w2v = w2v_model.wv

def get_vec(sent, model):
    words = list(jieba.cut(sent))
    vecs = [model[w] for w in words if w in model]
    return np.mean(vecs, axis=0) if vecs else np.zeros(300), words

v1, seg1 = get_vec(test_sent, w2v)
print("句子：", test_sent)
print("分词：", seg1)
print("维度：", v1.shape)

# ===================== GloVe=====================
print("\n======= GloVe 结果 =======")
glove_model = Word2Vec(sentences, vector_size=300, window=5, min_count=1)
glove = glove_model.wv

v2, seg2 = get_vec(test_sent, glove)
print("句子：", test_sent)
print("分词：", seg2)
print("维度：", v2.shape)

print("\n✅ 两个模型运行完成！")