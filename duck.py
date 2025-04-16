from duckduckgo_search import DDGS

results = DDGS().text('lNoticias sobre ciencia, el universo, el espacio y exploracion espacial', region='wt-wt', safesearch='off', timelimit='y', max_results=10)

print(results)
