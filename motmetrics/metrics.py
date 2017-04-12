"""py-motmetrics - metrics for multiple object tracker (MOT) benchmarking.

Christoph Heindl, 2017
https://github.com/cheind/py-motmetrics
"""

import pandas as pd
import numpy as np
from collections import OrderedDict, Iterable
from motmetrics.mot import MOTAccumulator

class MetricsContainer:
    def __init__(self):
        self.metrics = {}

    def register(self, fnc, deps=None, name=None):
        assert not fnc is None, 'No function given for metric {}'.format(name)

        if deps is None:
            deps = []
        elif deps is 'auto':
            import inspect
            deps = inspect.getargspec(fnc).args[1:] # assumes dataframe as first argument

        if name is None:
            name = fnc.__name__ # Relies on meaningful function names, i.e don't use for lambdas

        self.metrics[name] = {
            'name' : name,
            'fnc' : fnc,
            'deps' : deps
        }

    @property
    def names(self):
        return [v['name'] for v in self.metrics.values()]

    def summarize(self, df, metrics=None):
        cache = {}

        if metrics is None:
            metrics = self.names

        for mname in metrics:
            cache[mname] = self._compute(df, mname, cache, parent='summarize')            

        return OrderedDict([(k, cache[k]) for k in metrics])
        
    def _compute(self, df, name, cache, parent=None):
        assert name in self.metrics, 'Cannot find metric {} required by {}.'.format(name, parent)
        minfo = self.metrics[name]
        vals = []
        for depname in minfo['deps']:
            if not depname in cache:
                cache[depname] = self._compute(df, depname, cache, parent=name)
            vals.append(cache[depname])
        return minfo['fnc'](df, *vals)

def num_frames(df):
    return float(df.index.get_level_values(0).unique().shape[0])

def obj_frequencies(df):
    return df.OId.value_counts()

def num_unique_objects(df, obj_frequencies):
    return float(len(obj_frequencies))

def num_matches(df):
    return float(df.Type.isin(['MATCH']).sum())

def num_switches(df):
    return float(df.Type.isin(['SWITCH']).sum())

def num_falsepositives(df):
    return float(df.Type.isin(['FP']).sum())

def num_misses(df):
    float(df.Type.isin(['MISS']).sum())

def num_detections(df, num_matches, num_switches):
    return num_matches + num_switches

def num_objects(df):
    return float(df.OId.count())

def track_ratios(df, obj_frequencies):    
    tracked = data[df.Type !='MISS']['OId'].value_counts()   
    return tracked.div(obj_frequencies).fillna(1.)

def mostly_tracked(df, track_ratios):
    return track_ratio[track_ratios >= 0.8].count()

def partially_tracked(df, track_ratios):
    return track_ratios[(track_ratios >= 0.2) & (track_ratios < 0.8)].count()

def mostly_lost(df, track_ratios):
    return track_ratio[track_ratio < 0.2].count()

def num_fragmentation(df, obj_frequencies):
    fra = 0
    for o in obj_frequencies.index:
        # Find first and last time object was not missed (track span). Then count
        # the number switches from NOT MISS to MISS state.
        dfo = df[df.OId == o]
        notmiss = dfo[dfo.Type != 'MISS']
        if len(notmiss) == 0:
            continue
        first = notmiss.index[0]
        last = notmiss.index[-1]
        diffs = dfo.loc[first:last].Type.apply(lambda x: 1 if x == 'MISS' else 0).diff()
        fra += diffs[diffs == 1].count()
    return fra

def motp(df, num_detections):
    return df['D'].sum() / num_detections

def mota(df, num_misses, num_switches, num_falsepositives, num_objects):
    return 1. - (num_misses + num_switches + num_falsepositives) / num_objects

def precision(df, num_detections, num_falsepositives):
    return num_detections / (num_falsepositives + num_detections)

def recall(df, num_detections, num_objects):
    return num_detections / num_objects


def default_metrics():
    m = MetricsContainer()

    m.register(num_frames)
    m.register(obj_frequencies)    
    m.register(num_matches)
    m.register(num_switches)
    m.register(num_falsepositives)
    m.register(num_misses)
    m.register(num_detections)
    m.register(num_objects)
    m.register(num_unique_objects, deps='auto')
    m.register(track_ratios, deps='auto')
    m.register(mostly_tracked, deps='auto')
    m.register(partially_tracked, deps='auto')
    m.register(mostly_lost, deps='auto')
    m.register(num_fragmentation, deps='auto')
    m.register(motp, deps='auto')
    m.register(mota, deps='auto')
    m.register(precision, deps='auto')
    m.register(recall, deps='auto')

    return m



def compute_metrics(data):
    """Returns computed metrics for event data frame.

    Params
    ------
    data : pd.DataFrame or MOTAccumulator
        Events data frame to compute metrics for.
    
    Returns
    -------
    metr : dict
        Dictionary of computed metrics. Currently the following metrics are computed as fields
        in the dictionary

        - `Frames` total number of frames
        - `Match` total number of matches
        - `Switch` total number of track switches
        - `FalsePos` total number of false positives, i.e false alarms
        - `Miss` total number of misses
        - `MOTA` Tracker accuracy as defined in [1]
        - `MOTP` Tracker precision as defined in [1]. Since motmetrics is distance agnostic,
        this value depends on the distance and threshold on distance used. To compare this value to
        results from MOTChallenge 2D use 1.-MOTP
        - `Precision` Percent of correct detections to total tracker detections
        - `Recall` Percent of correct detections to total number of objects
        - `Frag` Number of track fragmentations as defined in [2]
        - `Objs` Total number of unique objects
        - `MT` Number of mostly tracked targets as defined in [2,3]
        - `PT` Number of partially tracked targets as defined in [2,3]
        - `ML´ Number of mostly lost targets as defined in [2, 3]

    References
    ----------
    1. Bernardin, Keni, and Rainer Stiefelhagen. "Evaluating multiple object tracking performance: the CLEAR MOT metrics." 
    EURASIP Journal on Image and Video Processing 2008.1 (2008): 1-10.
    2. Milan, Anton, et al. "Mot16: A benchmark for multi-object tracking." arXiv preprint arXiv:1603.00831 (2016).
    3. Li, Yuan, Chang Huang, and Ram Nevatia. "Learning to associate: Hybridboosted multi-target tracker for crowded scene." 
    Computer Vision and Pattern Recognition, 2009. CVPR 2009. IEEE Conference on. IEEE, 2009.
    """

    if isinstance(data, MOTAccumulator):
        data = data.events

    savediv = lambda a,b: a / b if b != 0 else np.nan

    # Common values
    
    nframes = float(data.index.get_level_values(0).unique().shape[0]) # Works for Dataframes and slices
    nmatch = float(data.Type.isin(['MATCH']).sum())
    nswitch = float(data.Type.isin(['SWITCH']).sum())
    nfp = float(data.Type.isin(['FP']).sum())
    nmiss = float(data.Type.isin(['MISS']).sum())
    nc = float(nmatch + nswitch)
    ng = float(data['OId'].count())

    # Compute MT, PT, ML
    # First count for each object the number of total occurrences. Next count for each object the 
    # number of times a correspondence was assigned. The track ratio corresponds to assigned / total 
    # for each object separately. Finally classify into MT, PT, ML (see further below).
    # Also account for cases when an object is never missed (fillna below).
    objs = data['OId'].value_counts()
    tracked = data[data.Type !='MISS']['OId'].value_counts()   
    track_ratio = tracked.div(objs).fillna(1.)

    # Compute fragmentation
    fra = 0
    for o in objs.index:
        # Find first and last time object was not missed (track span). Then count
        # the number switches from NOT MISS to MISS state.
        dfo = data[data.OId == o]
        notmiss = dfo[dfo.Type != 'MISS']
        if len(notmiss) == 0:
            continue
        first = notmiss.index[0]
        last = notmiss.index[-1]
        diffs = dfo.loc[first:last].Type.apply(lambda x: 1 if x == 'MISS' else 0).diff()
        fra += diffs[diffs == 1].count()
        
    metr = OrderedDict() # Use ordered dict to column order is preserved.
    metr['Frames'] = int(nframes)
    metr['Match'] = int(nmatch)
    metr['Switch'] = int(nswitch)
    metr['FalsePos'] = int(nfp)
    metr['Miss'] = int(nmiss)
    metr['MOTP'] = savediv(data['D'].sum(), nc)
    metr['MOTA'] = 1. - savediv(nmiss + nswitch + nfp, ng)
    metr['Precision'] = savediv(nc, nfp + nc)
    metr['Recall'] = savediv(nc, ng)
    metr['Frag'] = fra
    metr['Objs'] = len(objs)        
    metr['MT'] = track_ratio[track_ratio >= 0.8].count()
    metr['PT'] = track_ratio[(track_ratio >= 0.2) & (track_ratio < 0.8)].count()
    metr['ML'] = track_ratio[track_ratio < 0.2].count()

    return metr

def summarize(accs, names=None):
    """Compute event statistics of one or more MOT accumulators.
    
    Params
    ------
    accs : MOTAccumulator or list thereof
        Event accumulators to summarize.

    Kwargs
    ------
    names : string or list thereof, optional
        Name for accumulators

    Returns
    -------
    summary : pd.DataFrame
        A dataframe having metrics in columns and accumulator
        results in rows (one per accumulator). See `compute_metrics`
        for docs on available metrics.
    """
    
    if isinstance(accs, (MOTAccumulator, pd.DataFrame)):
        accs = [accs]

    if names is None:
        names = list(range(len(accs)))
    elif not isinstance(names, Iterable):
        names = [names]

    events = []
    for idx, d in enumerate(accs):
        events.append(d.events if isinstance(d, MOTAccumulator) else d)  
        
    dfs = []
    for name, ev in zip(names, events):
        dfs.append(pd.DataFrame(compute_metrics(ev), index=[name]))
    return pd.concat(dfs)

