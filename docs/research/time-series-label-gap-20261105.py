"""Offline synthetic boundary experiment, not a JEI backtest or OOS certificate.

Reproduce with Python and scikit-learn==1.8.0:
    python docs/research/time-series-label-gap-20261105.py
No network, market prices, private holdings, trades or strategy tuning are used.
"""
import hashlib
import inspect
import json
import sklearn
from sklearn.model_selection import TimeSeriesSplit

SESSIONS=120
FOLDS=3
TEST_SESSIONS=15
HORIZONS=(3,7,15,30,60)


def case(rows_per_session,horizon,gap):
    rows=list(range(SESSIONS*rows_per_session))
    result=[]
    split=TimeSeriesSplit(n_splits=FOLDS,test_size=TEST_SESSIONS*rows_per_session,gap=gap)
    for fold,(train,test) in enumerate(split.split(rows),start=1):
        test_start=int(test[0])//rows_per_session
        # A horizon label is known only after that session's close. Requiring
        # label_end < test_start conservatively excludes the boundary itself.
        overlaps=sum(int(row)//rows_per_session+horizon>=test_start for row in train)
        immature=sum(int(row)//rows_per_session+horizon>=SESSIONS for row in test)
        result.append({'fold':fold,'train_rows':len(train),'test_rows':len(test),
                       'last_train_session':int(train[-1])//rows_per_session,
                       'first_test_session':test_start,'last_test_session':int(test[-1])//rows_per_session,
                       'training_labels_reaching_test':overlaps,
                       'test_labels_not_yet_observable_at_end':immature})
    return {'rows_per_session':rows_per_session,'horizon_sessions':horizon,
            'gap_rows':gap,'folds':result,
            'training_labels_reaching_test':sum(x['training_labels_reaching_test']for x in result)}


def experiment():
    single=[]
    for horizon in HORIZONS:
        variants=[case(1,horizon,gap)for gap in (0,horizon-1,horizon)]
        assert all(x['training_labels_reaching_test']>0 for x in variants[:2])
        assert variants[1]['training_labels_reaching_test']==FOLDS
        assert variants[2]['training_labels_reaching_test']==0
        single.extend(variants)
    grouped=[]
    for horizon in (3,7,15,30):
        wrong=case(4,horizon,horizon)
        aligned=case(4,horizon,horizon*4)
        assert wrong['training_labels_reaching_test']>0
        assert aligned['training_labels_reaching_test']==0
        grouped.extend((wrong,aligned))
    # With four rows per session, a row gap is not a trading-session gap.
    # Real variable holding times require interval purging and date grouping;
    # no fixed row gap here establishes that real JEI data is leakage-free.
    return {'scope':'synthetic_split_boundary_only','market_performance':False,
            'qualified_oos_trades_added':0,'sessions':SESSIONS,'folds':FOLDS,
            'test_sessions_per_fold':TEST_SESSIONS,'sklearn_version':sklearn.__version__,
            'installed_splitter_sha256':hashlib.sha256(inspect.getsource(TimeSeriesSplit).encode()).hexdigest(),
            'single_row_per_session':single,'four_rows_per_session':grouped,
            'limitations':['No market returns, execution or regime validation.',
                           'No publication-time or survivorship audit.',
                           'Terminal test labels may remain immature and must not be scored.',
                           'Date grouping and actual label-end purging still required for JEI.']}


if __name__=='__main__':
    print(json.dumps(experiment(),ensure_ascii=False,indent=2))
