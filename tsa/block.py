#!/usr/bin/python
# -*- coding: utf-8 -*-

# Block class, called by Condition

import logging
from .error import TsaErrCollection
from .utils import to_pg_identifier
from .utils import with_errpointer

log = logging.getLogger(__name__)

class Block:
    """
    Represents a logical subcondition
    with information of site name and station id.
    See :py:class:``Condition`` that consists of blocks
    and operators and parentheses.
    A Block renders as boolean column in temporary db tables.
    For PostgreSQL compatibility, umlauts convert to a and o,
    and all strings are made lowercase.

    For a *primary* block, the ``raw_condition`` must consist of
    a station identifier, hashtag, sensor identifier,
    operator and a value.
    For a *secondary* block, the ``raw_condition`` must consist of
    a site identifier, hashtag and alias identifier. Note that these should
    refer to an existing Condition instance.

    :param master_alias: master alias identifier of the parent condition
    :type master_alias: string
    :param parent_site: site identifier of the parent condition
    :type parent_site: string
    :param order_nr: index of the block within the parent condition
    :type order_nr: integer
    :param raw_logic: logic to parse, bound to single sensor or existing Condition
    :type raw_logic: string
    """
    def __init__(self, master_alias, parent_site, order_nr, raw_logic):
        self.raw_logic = raw_logic
        self.master_alias = to_pg_identifier(master_alias)
        self.parent_site = to_pg_identifier(parent_site)
        self.order_nr = order_nr
        self.alias = self.master_alias + '_' + str(order_nr)
        self.secondary = None
        self.site = None
        self.station = None
        self.station_id = None
        self.source_alias = None
        self.source_view = None
        self.sensor = None
        self.sensor_id = None
        self.operator = None
        self.value_str = None

        self.errors = TsaErrCollection(f'BLOCK <{self.alias}>')

        # Set values depending on raw logic given
        self.unpack_logic()

    def is_valid(self):
        """
        Sanity check: is Block ready for analysis?
        """
        if self.secondary is None:
            self.errors.add(
                msg='Type of Block is None (should be .secondary == True or False)',
                log_add='error'
            )
        if self.secondary is False and self.sensor_id is None:
            self.errors.add(
                msg='Block has no sensor id',
                log_add='error'
            )
        # Add more here if needed; .errors cover quite a bit, though
        return len(self.errors) == 0

    def unpack_logic(self):
        """
        Detects and sets block type and attributes from raw logic string
        and checks validity of the attributes.

        .. note:: Following binary operators are considered:
            `'=', '<>', '>', '<', '>=', '<=', 'in'`.
            `between` is currently not supported.
            If operator is `in`, it is checked whether the value after it
            is a valid SQL tuple.
            Operator MUST be surrounded by whitespaces!

        :param raw_logic: original logic string
        :type raw_logic: string
        """
        binops = [' = ', ' <> ', ' > ', ' < ', ' >= ', ' <= ', ' in ']

        # ERROR if too many hashtags or operators
        n_hashtags = self.raw_logic.count('#')
        if n_hashtags > 1:
            self.errors.add(
                msg='Too many "#" symbols, only one or zero allowed',
                log_add='error'
            )
        n_binops = 0
        binop_in_str = None
        for binop in binops:
            if binop in self.raw_logic:
                n_binops += self.raw_logic.count(binop)
                binop_in_str = binop
        if n_binops > 1:
            self.errors.add(
                msg='Too many "=", "<>", ">", "<", ">=", "<=", "in" operators, only one or zero allowed',
                log_add='error'
            )

        # Case 1: contains no hashtag and no binary operator
        # -> secondary block, site is picked from parent_site.
        # Must NOT contain binary operator.
        if n_hashtags == 0 and n_binops == 0:
            self.secondary = True
            self.site = self.parent_site
            try:
                self.source_alias = to_pg_identifier(self.raw_logic)
                self.source_view = to_pg_identifier(f'{self.site}_{self.source_alias}')
            except:
                self.errors.add(
                    msg='Cannot set source alias and view for secondary condition',
                    log_add='exception'
                )

        # Case 2: contains hashtag but no binary operator
        # -> secondary block
        elif n_hashtags == 1 and n_binops == 0:
            self.secondary = True
            parts = self.raw_logic.split('#')
            try:
                self.site = to_pg_identifier(parts[0])
                self.source_alias = to_pg_identifier(parts[1])
                self.source_view = to_pg_identifier(f'{self.site}_{self.source_alias}')
            except:
                self.errors.add(
                    msg='Cannot set site, source alias and view for secondary condition',
                    log_add='exception'
                )

        # Case 3: contains hashtag and binary operator
        # -> primary block
        elif n_hashtags == 1 and n_binops == 1:
            self.secondary = False
            self.site = self.parent_site
            parts = self.raw_logic.split('#')
            parts = [parts[0]] + parts[1].split(binop_in_str)
            try:
                self.station = to_pg_identifier(parts[0])
                self.station_id = int(''.join(i for i in self.station if i.isdigit()))
                self.sensor = to_pg_identifier(parts[1])
                self.operator = binop_in_str.lower().strip()
                self.value_str = parts[2].lower().strip()
            except:
                self.errors.add(
                    msg='Cannot set attributes for primary condition',
                    log_add='exception'
                )

            # Special case with operator "in":
            # must be followed by tuple enclosed with parentheses.
            if self.operator == 'in':
                val_sw = self.value_str.startswith('(')
                val_ew = self.value_str.endswith(')')
                if not all ( (val_sw, val_ew) ):
                    self.errors.add(
                        msg='"in" must be followed by values enclosed by "()"',
                        log_add='error'
                    )

        # Case 4: ERROR if binary operator but no hashtag
        else:
            self.errors.add(
                msg='Primary Block requires a "#" between station and sensor',
                log_add='error'
            )

    def set_sensor_id(self, nameid_pairs):
        """
        Set sensor id based on name-id dict,
        presumably gotten from database.
        """
        if not self.secondary:
            try:
                self.sensor_id = nameid_pairs[self.sensor]
            except KeyError:
                self.errors.add(
                    msg=f'No sensor id found by sensor name "{self.sensor}"',
                    log_add='error'
                )

    def get_sql_def(self):
        """
        Create SQL call
        to be used as part of the corresponding
        Condition table creation.
        """
        if not self.is_valid():
            raise Exception(f'Block "{self.alias}" is not valid (see Block errors)')

        elif self.secondary:
            # Block is SECONDARY -> try to pick boolean values
            # and time ranges from existing db view
            sql = ("SELECT tstzrange(vfrom, vuntil) AS valid_r, "
                   f"master AS {self.alias} "
                   f"FROM {self.source_view}")

        else:
            # Block is PRIMARY -> make pack_ranges call
            # to form time ranges and boolean values
            sql = (f"SELECT valid_r, istrue AS {self.alias} "
                   "FROM pack_ranges("
                   "p_obs_relation := 'obs_main', "
                   "p_maxminutes := 30, "
                   f"p_statid := {self.station_id}, "
                   f"p_seid := {self.sensor_id}, "
                   f"p_operator := '{self.operator}', "
                   f"p_seval := '{self.value_str}')")

        return sql

    def __str__(self):
        if self.secondary is None:
            s = '<? '
        elif self.secondary is True:
            s = '<Secondary '
        else:
            s = '<Primary '
        s += f'Block {self.alias}> at {self.parent_site}: "{self.raw_logic}">'
        return s

    def __eq__(self, other):
        """
        The `==` method; two blocks are equal if their attributes
        are equal, **including the order number in ** `self.alias`.
        """
        return self.__dict__ == other.__dict__
