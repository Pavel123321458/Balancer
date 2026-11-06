"""Build additive facts for the pivot table from the vertical mart."""


def aggregate(cursor, run_id, params):
    cursor.execute(
        """INSERT INTO pivot_facts
            (run_id, PREFIX, CLASS, SUFFIX, ARRAY_KEY, `KEY`, VALUE_ADJUSTED, DIFF_FLAG, SOURCE, CNT)
           SELECT n.run_id, n.PREFIX, n.CLASS, n.SUFFIX, n.ARRAY_KEY, n.`KEY`,
                  n.ADJUSTED_VALUE, c.DIFF_FLAG, n.SOURCE, COUNT(DISTINCT n.APP_ID)
           FROM normalized n JOIN comparisons c USING (run_id, APP_ID, PATH, ARRAY_KEY)
           WHERE n.run_id = %s
           GROUP BY n.run_id, n.PREFIX, n.CLASS, n.SUFFIX, n.ARRAY_KEY, n.`KEY`,
                    n.ADJUSTED_VALUE, c.DIFF_FLAG, n.SOURCE""", (run_id,),
    )

