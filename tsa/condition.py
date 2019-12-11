#!/usr/bin/python
# -*- coding: utf-8 -*-

# Condition class, called by CondCollection

import logging
import re
import pandas
import psycopg2
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from .block import Block
from .error import TsaErrCollection
from .utils import to_pg_identifier
from .utils import eliminate_umlauts
from .utils import trunc_str
from matplotlib import rcParams
from datetime import timedelta
from collections import OrderedDict

log = logging.getLogger(__name__)

# Set matplotlib parameters globally
rcParams['font.family'] = 'sans-serif'
rcParams['font.sans-serif'] = ['Arial', 'Tahoma']

class Condition:
    """
    Logical combination of Blocks.
    Represented by one Excel row.

    :param site: site / location / area identifier
    :type site: string
    :param master_alias: master alias identifier
    :type master_alias: string
    :param raw_condition: condition definition
    :type raw_condition: string
    :param time_range: start (included) and end (included) timestamps
    :type time_range: list or tuple of datetime objects
    :param excel_row: row index referring to the source of the condition in Excel file
    :type excel_row: integer
    """
    def __init__(self, site, master_alias, raw_condition, time_range, excel_row=None):
        # Attrs for further use must be PostgreSQL compatible
        self.site = to_pg_identifier(site)
        self.master_alias = to_pg_identifier(master_alias)
        self.id_string = to_pg_identifier(f'{self.site}_{self.master_alias}')

        self.condition = eliminate_umlauts(raw_condition).strip().lower()

        # Times must be datetime objects
        self.time_from = time_range[0]
        self.time_until = time_range[1]

        # As above but representing actual min and max time of result data
        self.data_from = None
        self.data_until = None

        # Excel row for prompting, if made from Excel sheet
        self.excel_row = excel_row

        self.errors = TsaErrCollection(str(self))

        # Following attrs will be set by .make_blocks method
        self.blocks = OrderedDict()
        self.alias_condition = ''
        self.secondary = None
        self.blocks_made = False
        self.make_blocks()

        # pandas DataFrames for results
        self.main_df = pandas.DataFrame()

        # Total time will be set to represent
        # actual min and max timestamps of the data
        self.tottime = self.time_until - self.time_from
        self.tottime_valid = timedelta(0)
        self.tottime_notvalid = timedelta(0)
        self.tottime_nodata = self.tottime
        self.percentage_valid = 0
        self.percentage_notvalid = 0
        self.percentage_nodata = 1

    def validate_order(self, tuples):
        """
        Validate order of the elements of a :py:class:``Block``.

        :param tuples: list of tuples, each of which has
            ``open_par`, ``close_par``, ``andor``, ``not`` or ``block``
            in the first index and the string element itself in the second.
        :type tuples: list or tuple
        :return: ``False`` if there were erroneous elements, ``True`` otherwise

        Following element types may be in the first index:
            ``open_par``, ``not``, ``block``

        Following elements may be in the last index:
            ``close_par``, ``block``

        For elements other than the last one, see the table below
        to see what element can follow each element.
        Take the first element from left and the next element from top.

        +-------------+------------+-------------+---------+-------+---------+
        |             | `open_par` | `close_par` | `andor` | `not` | `block` |
        +=============+============+=============+=========+=======+=========+
        | `open_par`  | OK         | X           | X       | OK    | OK      |
        +-------------+------------+-------------+---------+-------+---------+
        | `close_par` | X          | OK          | OK      | X     | X       |
        +-------------+------------+-------------+---------+-------+---------+
        | `andor`     | OK         | X           | X       | OK    | OK      |
        +-------------+------------+-------------+---------+-------+---------+
        | `not`       | OK         | X           | X       | X     | OK      |
        +-------------+------------+-------------+---------+-------+---------+
        | `block`     | X          | OK          | OK      | X     | X       |
        +-------------+------------+-------------+---------+-------+---------+
        """
        success = True
        allowed_first = ('open_par', 'not', 'block')
        allowed_pairs = (
        ('open_par', 'open_par'), ('open_par', 'not'), ('open_par', 'block'),
        ('close_par', 'close_par'), ('close_par', 'andor'),
        ('andor', 'open_par'), ('andor', 'not'), ('andor', 'block'),
        ('not', 'open_par'), ('not', 'block'),
        ('block', 'close_par'), ('block', 'andor')
        )
        allowed_last = ('close_par', 'block')
        last_i = len(tuples) - 1

        for i, el in enumerate(tuples):
            if i == 0:
                if el[0] not in allowed_first:
                    self.errors.add(
                        msg=f'"{el[1]}" cannot be first element in condition',
                        log_add='error'
                    )
                    success = False
            elif i == last_i:
                if el[0] not in allowed_last:
                    self.errors.add(
                        msg=f'"{el[1]}" cannot be last element in condition',
                        log_add='error'
                    )
                    success = False
            if i < last_i:
                if (el[0], tuples[i+1][0]) not in allowed_pairs:
                    self.errors.add(
                        msg=f'Illegal combination in condition: "{el[1]}" before "{tuples[i+1][1]}" ',
                        log_add='error'
                    )
                    success = False

        return success

    def make_blocks(self):
        """
        Extract a list of Block instances (that is, subconditions)
        into ``self.blocks`` based on ``self.condition``,
        define ``self.alias_condition`` based on the aliases of the Block instances
        and detect condition type (``secondary == True`` if any of the blocks has
        ``secondary == True``, ``False`` otherwise).
        """
        is_valid = True
        value = self.condition

        # Generally, opening and closing bracket counts must match
        n_open = value.count('(')
        n_close = value.count(')')
        if n_open != n_close:
            self.errors.add(
                msg=f'Unequal of "(" ({n_open}) and ")" ({n_close}) in condition',
                log_add='error'
            )
            is_valid = False

        # Eliminate multiple whitespaces
        # and leading and trailing whitespaces
        value = ' '.join(value.split()).strip()

        # Split by
        # - parentheses
        # - and, or, not: must be surrounded by spaces
        # - not: starting the string and followed by space.
        # Then strip results from trailing and leading whitespaces
        # and remove empty elements.
        sp = re.split(
        '([()]|(?<=\s)and(?=\s)|(?<=\s)or(?=\s)|(?<=\s)not(?=\s)|^not(?=\s))', value)
        sp = [el.strip() for el in sp]
        sp = [el for el in sp if el]

        # Handle special case of parentheses after "in":
        # they are part of the logic element.
        # Block() will detect in the next step
        # if the tuple after "in" is not correctly enclosed by ")".
        new_sp = []
        for el in sp:
            if not new_sp:
                new_sp.append(el)
                continue
            if len(new_sp[-1]) > 3 and new_sp[-1][-3:] == ' in':
                new_sp[-1] = new_sp[-1] + ' ' + el
            elif ' in ' in new_sp[-1] and new_sp[-1][-1] != ')':
                new_sp[-1] = new_sp[-1] + el
            else:
                new_sp.append(el)

        # Identify the "role" of each element by making them into
        # tuples like (role, element).
        # First, mark parentheses and and-or-not operators.
        # The rest should convert to logic blocks;
        # Block() raises error if this does not succeed.
        idfied = []
        i = 0
        tokens = {'(': 'open_par',
                  ')': 'close_par',
                  'and': 'andor',
                  'or': 'andor',
                  'not': 'not'}
        for el in new_sp:
            if el in tokens.keys():
                idfied.append( (tokens[el], el) )
            else:
                try:
                    bl = Block(master_alias=self.master_alias,
                        parent_site=self.site,
                        order_nr=i,
                        raw_logic=el)
                    # If a block with same contents already exists,
                    # do not add a new one with another order number i,
                    # but add the existing block with its order number.
                    # The .index() method raises an error in case the tuple with
                    # Block element is NOT contained in the list.
                    existing_blocks = [t for t in idfied if t[0] == 'block']
                    for eb in existing_blocks:
                        if eb[1].raw_logic == bl.raw_logic:
                            idfied.append(eb)
                            break
                    else:
                        idfied.append(('block', bl))
                        i += 1
                except:
                    self.errors.add(
                        msg=f'Cannot create Block from "{el}"',
                        log_add='exception'
                    )
                    is_valid = False

        # Check the correct order of the tuples.
        # This should raise and error and thus exit the method
        # if there is an illegal combination of elements next to each other.
        is_valid = is_valid and self.validate_order(idfied)

        # Also check if all Blocks are marked valid
        is_valid = is_valid and all(el[1].secondary is not None for el in idfied if el[0] == 'block')

        # If validation was successful, attributes can be set

        # Pick up all unique blocks in the order they appear
        blocks = OrderedDict()
        for el in idfied:
            if el[0] == 'block' and el[1].alias not in blocks.keys():
                blocks[el[1].alias] = el[1]
        self.blocks = blocks
        if len(self.blocks) == 0:
            self.errors.add(
                msg='No Blocks were created',
                log_add='warning'
            )
            is_valid = False

        # Form the alias condition by constructing the parts back
        # from the "identified" parts, but for blocks, this time
        # use their alias instead of the raw condition string.
        # Whitespaces must be added a bit differently for each type.
        alias_parts = []
        for el in idfied:
            if el[0] == 'andor':
                alias_parts.append(f' {el[1]} ')
            elif el[0] == 'not':
                alias_parts.append(f'{el[1]} ')
            elif el[0] in ('open_par', 'close_par'):
                alias_parts.append(el[1])
            elif el[0] == 'block':
                alias_parts.append(el[1].alias)
        self.alias_condition = ''.join(alias_parts)

        # If any of the blocks is secondary,
        # then the whole condition is considered secondary.
        self.secondary = False
        for bl in self.blocks.values():
            if bl.secondary:
                self.secondary = True
                break

        # Finally, inform the object if the condition is valid
        # and further analysis is thus possible
        self.blocks_made = is_valid
        if not is_valid:
            self.errors.add(
                msg=('There were errors with this condition '
                     'and it will not be analyzed'),
                log_add='warning'
            )
        else:
            log.debug(f'{str(self)} parsed successfully')

    def get_station_ids_in_blocks(self):
        """
        Return unique station ids contained by primary Blocks
        """
        stids = set()
        for bl in self.blocks.values():
            if not bl.secondary:
                stids.add(bl.station_id)
        return stids

    def create_db_temptable(self, pg_conn=None):
        """
        Create temporary table corresponding to the condition.
        If ``pg_conn`` is ``None``, no database queries are executed;
        if ``verbose`` is ``True``, whole SQL query is logged.
        If condition is secondary and referenced relations do not exist
        in database, running the SQL query will fail.
        """
        log.info(f'Creating temp table {self.id_string}')

        drop_sql = f"DROP TABLE IF EXISTS {self.id_string};\n"

        # Block-related data structures in the db are defined as temp tables
        # whose lifespan only covers the current transaction:
        # this prevents namespace conflicts with, e.g., similar aliases shared by multiple sites
        # and keeps the identifier reasonably short. Moreover, Block-related
        # datasets are not needed between Conditions (-> db sessions) as such.
        block_defs = []
        # ALL blocks must qualify, otherwise analyzing the condition is rejected
        try:
            for bl in self.blocks.values():
                s = f"CREATE TEMP TABLE {bl.alias} ON COMMIT DROP AS ({bl.get_sql_def()});"
                block_defs.append(s)
        except:
            self.errors.add(
                msg='Cannot build Block SQL definition, skipping temp table creation',
                log_add='exception'
            )
            return

        # Temp table representing the Condition persists along with the connection / session,
        # and it is constructed as follows:
        # - Make the Block parts (dropped at the end of the transaction)
        # - Create the "most granular" validity ranges series from all the Block temp tables as "master_ranges"
        # - Left join the Block temp tables to master_ranges
        # If there is only one Block, master_ranges is not needed.
        create_sql = "\n".join(block_defs)

        if len(self.blocks) == 1:
            create_sql += (f"\nCREATE TEMP TABLE {self.id_string} AS ( \n"
                           "SELECT \n"
                           "lower(valid_r) AS vfrom, \n"
                           "upper(valid_r) AS vuntil, \n"
                           "upper(valid_r)-lower(valid_r) AS vdiff, \n"
                           f"{self.blocks.keys()[0]}, \n"
                           f"{self.blocks.keys()[0]} AS master \n"
                           f"FROM {self.blocks.keys()[0]});")
        else:
            master_seq_els = []
            for bl in self.blocks.values():
                s = f"SELECT unnest( array [lower(valid_r), upper(valid_r)] ) AS vt FROM {bl.alias}"
                master_seq_els.append(s)
            master_seq_sql = "\nUNION \n".join(master_seq_els)
            create_sql += (f"\nCREATE TEMP TABLE {self.id_string} AS ( \n"
                           "WITH master_seq AS ( \n"
                           f"{master_seq_sql} \n"
                           "ORDER BY vt), \n")
            create_sql += ("master_ranges_wlastnull AS ( \n"
                           "SELECT vt AS vfrom, LEAD(vt, 1) OVER (ORDER BY vt) AS vuntil \n"
                           "FROM master_seq), \n")
            create_sql += ("master_ranges AS ( \n"
                           "SELECT tstzrange(vfrom, vuntil) AS valid_r \n"
                           "FROM master_ranges_wlastnull \n"
                           "WHERE vuntil IS NOT NULL) \n")
            block_join_els = ['master_ranges']
            for bl in self.blocks.values():
                s = f"LEFT JOIN {bl.alias} ON master_ranges.valid_r && {bl.alias}.valid_r"
                block_join_els.append(s)
            block_join_sql = " \n".join(block_join_els)
            create_sql += ("SELECT \n"
                           "lower(master_ranges.valid_r) AS vfrom, \n"
                           "upper(master_ranges.valid_r) AS vuntil, \n"
                           "upper(master_ranges.valid_r)-lower(master_ranges.valid_r) AS vdiff, \n")
            create_sql +=  ", \n".join([f"{bl.alias}" for bl in self.blocks.values()]) + ", \n"
            create_sql += f"({self.alias_condition}) AS master \nFROM {block_join_sql});"

        log.debug('\n' + drop_sql)
        log.debug('\n' + create_sql)

        if pg_conn is None:
            self.errors.add(
                msg='No pg_conn: temp table creation SQL is not run',
                log_add='warning'
            )
        else:
            try:
                with pg_conn.cursor() as cur:
                    cur.execute(drop_sql)
                    pg_conn.commit()
                    cur.execute(create_sql)
                    pg_conn.commit()
                    log.info(f'Temp table created for {str(self)}')
            except:
                pg_conn.rollback()
                self.errors.add(
                    msg='Failed to create temp table',
                    log_add='exception'
                )

    def fetch_results_from_db(self, pg_conn):
        """
        Fetch result data from corresponding db view
        to pandas DataFrame, and set summary attribute values
        based on the DataFrame.
        """
        if not self.is_valid():
            return
        sql = f"SELECT * FROM {self.id_string};"
        try:
            self.main_df = pandas.read_sql(sql, con=pg_conn)
        except:
            self.errors.add(
                msg='Cannot not fetch results from db',
                log_add='exception'
            )
            return
        df = self.main_df

        self.data_from = df['vfrom'].min()
        self.data_until = df['vuntil'].max()
        if not (self.data_from is None or self.data_until is None):
            self.tottime = self.data_until - self.data_from

        self.tottime_valid = df[df['master']==True]['vdiff'].sum() or timedelta(0)
        self.tottime_notvalid = df[df['master']==False]['vdiff'].sum() or timedelta(0)
        self.tottime_nodata = self.tottime - self.tottime_valid - self.tottime_notvalid
        tts = self.tottime.total_seconds()
        self.percentage_valid = self.tottime_valid.total_seconds() / tts
        self.percentage_notvalid = self.tottime_notvalid.total_seconds() / tts
        self.percentage_nodata = self.tottime_nodata.total_seconds() / tts

    def get_timelineplot(self):
        """
        Returns a Matplotlib figure object:
        a `broken_barh` plot of the validity of the condition
        and its blocks on a timeline.
        """
        if self.main_df.empty:
            raise Exception('main_df is empty, cannot make timeline plot')

        def getfacecolor(val):
            """
            Return a color name
            by boolean column value.
            """
            if val == True:
                return '#f03b20'
            elif val == False:
                return '#2b83ba'
            return '#bababa'

        # Set height and transparency for block rows, between 0-1;
        # master row will be set to height 0.8 and alpha 1 below.
        hgtval = 0.5
        alphaval = 0.5
        # Offset of the logic label above the bar
        lbl_offset = 0.1

        # Make matplotlib-ready range list from the time columns
        xr = zip([mdates.date2num(el) for el in self.main_df['vfrom']],
                 [mdates.date2num(el) for el in self.main_df['vuntil']])
        xr = [(a, b-a) for (a, b) in xr]

        # Make subplots for blocks;
        # for every block, there should be
        # a corresponding boolean column in the result DataFrame!
        fig, ax = plt.subplots()
        yticks = []
        ylabels = []
        i = 1
        for bl in self.blocks.values():
            logic_lbl = bl.raw_logic
            ax.broken_barh(xranges=xr, yrange=(i, hgtval),
                           facecolors=list(map(getfacecolor,
                                               self.main_df[bl.alias])),
                           alpha=alphaval)
            ax.annotate(s=logic_lbl,
                        xy=(xr[0][0], i + hgtval + lbl_offset))
            yticks.append(i + (hgtval / 2))
            ylabels.append(bl.alias)
            i += 1

        # Add master row to the plot
        hgtval = 0.8
        ax.broken_barh(xranges=xr, yrange=(i, hgtval),
                       facecolors=list(map(getfacecolor,
                                           self.main_df['master'])))
        ax.annotate(s=self.alias_condition,
                    xy=(xr[0][0], i + hgtval + lbl_offset))
        yticks.append(i + (hgtval / 2))
        ylabels.append('master')
        i += 1

        # Set a whole lot of axis parameters...
        ax.set_axisbelow(True)

        ax.xaxis_date()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%y'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_ticks_position('none')
        ax.xaxis.grid(color='#e5e5e5')
        #plt.xticks(rotation=45)

        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels)
        ax.yaxis.set_ticks_position('none')

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_visible(False)
        ax.spines['bottom'].set_visible(False)

        return ax

    def save_timelineplot(self, fobj, w, h):
        """
        Save main timeline plot as png picture into given file object
        with given pixel dimensions.

        :return: ``True`` if saved successfully, ``False`` otherwise
        """
        DPI = 300
        w = w / DPI
        h = h / DPI
        try:
            fig = self.get_timelineplot().get_figure()
            fig.dpi = DPI
            fig.set_size_inches(w, h)
            fig.savefig(fname=fobj,
                        format='png')
            plt.close(fig)
            return True
        except:
            self.errors.add(
                msg='Cannot save timeline plot',
                log_add='exception'
            )
            return False

    def is_valid(self):
        """
        Sanity check of properties needed for further steps.
        """
        blocks_valid = all(bl.is_valid() for bl in self.blocks.values())
        # Add more here if needed
        return blocks_valid and self.blocks_made

    def __getitem__(self, key):
        """
        Return Block from the OrderedDict referenced by ``key``.
        """
        return self.blocks[key]


    def __str__(self):
        if not hasattr(self, 'secondary') or self.secondary is None:
            s = '<? '
        elif self.secondary is True:
            s = '<Secondary '
        else:
            s = '<Primary '
        s += f'Condition {self.id_string} at Excel row {self.excel_row}>'
        return s
