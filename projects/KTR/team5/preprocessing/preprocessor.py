import logging
import sys
from time import perf_counter
from typing import Optional

import pandas as pd
from feature_engine.encoding import RareLabelEncoder, WoEEncoder
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import QuantileTransformer, StandardScaler


class ZeroVarRemover(TransformerMixin):
    __slots__ = '_sus', '_logger'

    def __init__(self):
        super().__init__()
        self._sus = None
        self._logger = logging.getLogger(__name__)

    def fit(self, x, y):
        __start = perf_counter()
        self._sus = x.loc[:, x.nunique() == 1]
        self._logger.debug(f"zerovarremover cols staged to be removed: {self._sus.columns.tolist()} ")
        return self

    def transform(self, x):
        return x.drop(self._sus, axis=1)


class OutlierTransformer(BaseEstimator, TransformerMixin):
    """
    Class finds and replaces values in quantile or 1-quantile with largest values that
    are not classified as outliers

    Parameters
    ----------
    skip: list[str] - list of names of columns to skip
    quantile: float - quantile to be classifier as outliers

    Attributes
    ----------
    quantile: float - quantile to be replaced
    skip: list[str] - list of columns to ignore

    """
    __slots__ = ('skip', 'quantile', '_limits', '_logger')

    def __init__(self, skip = None, quantile: float = .025) -> None:
        self.quantile = quantile
        self.skip = skip
        self._limits = None
        self._logger = logging.getLogger(__name__)

    def fit(self, X: pd.DataFrame, y: Optional[pd.DataFrame] = None):
        """
        Finds the limits of values which will be replaced

        Parameters
        ----------
        X: pandas.DataFrame - DataFrame to be transformed
        y: pandas.Series - Optional Series of target variable
        """
        __start = perf_counter()
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(X)
        self._logger.debug(f"Time of fitting OutlierTransformer: {perf_counter() - __start}")
        self._limits = pd.DataFrame(X.quantile(self.quantile))
        self._limits[1 - self.quantile] = X.quantile(1 - self.quantile).values
        if self.skip is not None:
            self._limits.loc[self.skip] = None
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Transforms the DataFrame

        Parameters
        ----------
        X: pandas.DataFrame - DataFrame to be transformed
        y: pandas.Series - Optional Series of target variable
        """
        __start = perf_counter()
        if not isinstance(X, pd.DataFrame):
            X = pd.DataFrame(X)
        q1 = self._limits.iloc[:, 0]
        q2 = self._limits.iloc[:, 1]
        outliers_low = X < q1
        X = X.mask(outliers_low, q1, axis=1)
        outliers_top = X > q2
        X = X.mask(outliers_top, q2, axis=1)
        self._logger.debug(f"Time of transforming OutlierTransformer: {perf_counter() - __start}")
        return X


class ignorer(TransformerMixin):
    """ignoruje wyj??tki xd i zpaisuje je do logu zamiast ko??czy?? wykonanie
    je??li zajdzie wyj??tek dalej przekazywane s?? poprzednie dane
    to jest na potrzeby RareLabelEncoder i WoEEncoder, poniewa?? rzucaj?? wyj??tek je??li w danych nie ma danych kategorycznych 
    a my chcemy ??eby dzia??a??o zawsze


    """
    __slots__ = ['_broken', '_logger', '_baseobj']

    def __init__(self, baseobj):
        """
        Parameters
        ----------
        baseobj: Any - Estymator/Transfomer z metodami fit(X,y)->Self i transform(X)->DataFrame
        """
        super().__init__()
        self._broken = False
        self._logger = logging.getLogger(__name__)
        try:
            self._baseobj = baseobj
        except:
            self._logger.warning("kwargs are broken")
            self._logger.warning(sys.exc_debug())
            self._broken = True
        finally:
            self._logger.debug(f"{baseobj} initialized")

    def fit(self, X, y):
        try:
            assert (self._broken == False)
            self._baseobj.fit(X, y)
        except AssertionError:
            self._logger.debug(f"{self._baseobj} is already broken")
            return
        except:
            self._broken = True
            self._logger.warning(f"{self._baseobj}fit is broken")
            self._logger.warning(sys.exc_debug())

        finally:
            return self

    def transform(self, X):
        try:
            assert (self._broken == False)
            return self._baseobj.transform(X)
        except AssertionError:
            self._logger.debug(f"{self._baseobj} is already broken")
        except:
            self._broken = True
            self._logger.warning(f"{self._baseobj}transform is broken")
            self._logger.warning(sys.exc_debug())
        finally:
            return X


class DataFramer(TransformerMixin):
    def fit(self, x, y):
        return self

    def transform(self, x):
        return pd.DataFrame(x)


def get_pre() -> Pipeline:
    return make_pipeline(
        DataFramer(),
        ZeroVarRemover(),  # usuni??cie zmiennych o zerowej wariancji
        SimpleImputer(strategy="most_frequent"),  # uzupe??nienie brak??w danych
        OutlierTransformer(),  # zast??pienie outlier??w warto??ciami skrajnymi
        ignorer(QuantileTransformer()),  # upodobnienie rozk??adu do rozk??adu normalnego
        ignorer(StandardScaler()),  # przeskalowanie do rozk??adu normalnego
        ignorer(RareLabelEncoder()),  # pogrupowanie rzadkich klas
        ignorer(WoEEncoder())  # zamienienie object??w ich woe
    )
