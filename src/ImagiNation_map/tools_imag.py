import dhlab as dh
import pandas as pd
import dhlab.graph_networkx_louvain as gnl
import networkx as nx
import requests
import json
from io import StringIO


def imag_corpus():
    res =  requests.get(f"{dh.constants.BASE_URL}/imagination/all")
    if res.status_code == 200:
        data = json.loads(res.text)
    else:
        data = "[]"
    return pd.DataFrame(data)

def geo_locations(dhlabid):
    res = requests.get(f"{dh.constants.BASE_URL}/imagination_geo_data", params={"dhlabid":dhlabid})
    if res.status_code == 200:
        data = pd.read_json(StringIO(res.text))
    else:
        data = pd.DataFrame()
    return data

def geo_locations_corpus(dhlabids):
    res = requests.post(f"{dh.constants.BASE_URL}/imagination_geo_data_list", json={"dhlabids":list(dhlabids)})
    if res.status_code == 200:
        data = pd.read_json(StringIO(res.text))
    else:
        print(res.status_code)
        data = pd.DataFrame()
    return data

def get_imag_corpus():
    im = imag_corpus()
    c = dh.Corpus()
    c.extend_from_identifiers(im.urn)
    corpus = c.frame
    corpus.dhlabid = corpus.dhlabid.astype(int)
    return corpus


def imag_corpus():
    return requests.get(f"{dh.constants.BASE_URL}/imagination/all")

def make_collocation_graph(corpus, target_word, top=15, before=4, after=4, ref = None, limit=1000):
    """Make a cascaded network of collocations ref is a frequency list"""
    

    coll = dh.Collocations(corpus, [target_word], before=before, after=after, samplesize=limit).frame
    
    if not ref is None:
        coll['counts'] = coll['counts']*100/coll['counts'].sum()
        coll['counts'] = coll['counts']/ref
        
    coll = coll.sort_values(by="counts", ascending = False)
    edges = []
    visited = []               
    for word in coll[:top].index:
        # loop gjennom kollokasjonen og lag en ny kollokasjon for hvert ord
        edges.append((target_word, word, coll.loc[word]))
        if word.isalpha() and not word in visited:
            subcoll = dh.Collocations(corpus, [word], before=before, after=after, samplesize=limit).frame        
            if not ref is None:
                subcoll['counts'] = subcoll['counts']*100/subcoll['counts'].sum()
                subcoll['counts'] = subcoll['counts']/ref

            for w in subcoll.sort_values(by="counts", ascending = False)[:top].index:
                if w.isalpha():
                    edges.append((word, w, subcoll.loc[w]))
            visited.append(word)
            #print(visited)
    target_graph = nx.Graph()
    target_graph.add_edges_from(edges)

    return target_graph

def make_imagination_corpus():
    """Bygg hele imagination-korpuset fra dhlab"""

    import requests
    def query_imag_corpus(category=None, author=None, title=None, year=None, publisher=None, place=None, oversatt=None):
        """Fetch data from imagination corpus"""
        params = locals()
        params = {key: params[key] for key in params if params[key] is not None}
        #print(params)
        r = requests.get(f"{dh.constants.BASE_URL}/imagination", params=params)
        return r.json()
   
    # kategoriene
    cats = [
        'Barnelitteratur',
        'Biografi / memoar',
        'Diktning: Dramatikk',
        'Diktning: Dramatikk # Diktning: oversatt',
        'Diktning: Epikk',
        'Diktning: Epikk # Diktning: oversatt',
        'Diktning: Lyrikk',
        'Diktning: Lyrikk # Diktning: oversatt',
        'Diverse',
        'Filosofi / estetikk / språk',
        'Historie / geografi',
        'Lesebok / skolebøker / pedagogikk',
        'Litteraturhistorie / litteraturkritikk',
        'Naturvitenskap / medisin',
        'Reiselitteratur',
        'Religiøse / oppbyggelige tekster',
        'Samfunn / politikk / juss',
        'Skisser / epistler / brev / essay / kåseri',
        'Taler / sanger / leilighetstekster',
        'Teknologi / håndverk / landbruk / havbruk'
    ]
   
    # bygg en dataramme for hver kategori
    a = dict()
    for c in cats:
        a[c] = dh.Corpus()
        a[c].extend_from_identifiers(query_imag_corpus(category=c))
        a[c] = a[c].frame
        a[c]['category'] = c

    # lim alt sammen til et stort korpus
    imag_all = pd.concat([a[c] for c in a])
    imag_all.year = imag_all.year.astype(int)
    imag_all.dhlabid = imag_all.dhlabid.astype(int)
   
    return imag_all
    
def corpus_ngram(
        corpus: pd.DataFrame,
        words: str,
        mode: str = 'rel'
):
    """Extract corpus-specific frequencies for given n-grams"""
    # Split the input words into a list of words
    search_terms = words.split(" ")

    # Create dataframe where the relevant years from the corpus are the index
    d2y = pd.Series(corpus.set_index('dhlabid')['year'].to_dict()).to_frame("year")
    # print(d2y)

    # Fetch frequencies from the corpus documents
    counts = api.get_document_frequencies(list(corpus.urn), words=search_terms)

    absfreq = counts['freq'].transpose().copy()
    absfreq_by_year = pd.concat([d2y, absfreq], axis=1
        ).groupby('year').sum().convert_dtypes()

    if mode.lower().startswith('r'):
        relfreq = counts['relfreq'].transpose().copy()
        # Calculate the total word frequency per urn
        urncounts = (absfreq / relfreq)
        # Group counts by year
        urncounts_by_year = pd.concat([d2y, urncounts], axis=1).groupby('year').sum()
        # Calculate relative frequency per year
        frek = (absfreq_by_year / urncounts_by_year) * 100
        # Ensure NaN-values are set to 0
        frek = frek.astype(float).fillna(0.0).astype(float)
    else:
        frek = absfreq_by_year.fillna(0)
    frek.index = frek.index.astype(int)
    return frek
    
def imag_ngram(corpus, words):
    cnts = dh.Counts(corpus, words)
    d2y = pd.Series(corpus.set_index('dhlabid')['year'].to_dict())
    d2y.to_frame('year')
    frek = cnts.frame.transpose().copy()
    frek = pd.concat([frek, d2y.to_frame('year')], axis = 1)
    return frek.groupby('year').sum()