from abc import abstractmethod
from typing import List, Optional

from pyspark.sql import DataFrame

from prophecy.config import ConfigBase
from threading import Lock

class MetaGemExec:
    def __init__(self, metrics_enabled=False, parent_unique_id=None):
        self.parent_unique_id = parent_unique_id
        self.metrics_enabled = metrics_enabled
        self.unique_id = 1
        self.lock = Lock()

    def increment_id(self):
        self.unique_id = self.unique_id + 1

    def get_unique_id(self):
        if self.parent_unique_id is not None:
            return str(self.parent_unique_id) + "." + str(self.unique_id)
        else:
            return str(self.unique_id)

    def get_and_increment_id(self):
        with self.lock:
            run_id = self.get_unique_id()
            self.increment_id()
            return run_id

    @abstractmethod
    def execute(self, spark, config: ConfigBase, unique_id, *inDFs: List[DataFrame]):
        pass

    @abstractmethod
    def execute(self, spark, config: ConfigBase, *inDFs: List[DataFrame]):
        pass

    def __run__(self, spark, config, *inDFs):
        result = None
        if self.metrics_enabled:
            current_unique_id = self.get_and_increment_id()
            result = self.execute(spark, config, current_unique_id, *inDFs)
        else:
            result = self.execute(spark, config, *inDFs)
        return result

def do_union(results: list, distinct=False):
    results = [x for x in results if x is not None]
    union_df = None
    if len(results) > 0:
        element_type = type(results[0])
        for element in results:
            if element_type != type(element):
                raise Exception("Distinct element types found in do_union() call")
        if isinstance(results[0], tuple) or isinstance(results[0], list):
            final_dfs: List[DataFrame] = list(results[0])
            for outer_index in range(1, len(results)):
                inner_index = 0
                for next_df in results[outer_index]:
                    if distinct:
                        final_dfs[inner_index] = final_dfs[inner_index].union(next_df).distinct()
                    else:
                        final_dfs[inner_index] = final_dfs[inner_index].union(next_df)
                    inner_index += 1
            union_df = tuple(final_dfs)
        else:
            final_df: DataFrame = results[0]
            for index in range(1, len(results)):
                if distinct:
                    final_df = final_df.union(results[index]).distinct()
                else:
                    final_df = final_df.union(results[index])
            union_df = (final_df,)
    else:
        union_df = tuple([])

    if union_df is not None and (len(union_df) == 1):
        return union_df[0]
    else:
        return union_df