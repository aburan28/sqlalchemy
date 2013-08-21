# sql/dml.py
# Copyright (C) 2009-2013 the SQLAlchemy authors and contributors <see AUTHORS file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: http://www.opensource.org/licenses/mit-license.php
"""
Provide :class:`.Insert`, :class:`.Update` and :class:`.Delete`.

"""

from .base import Executable, _generative, _from_objects
from .elements import ClauseElement, _literal_as_text, Null, and_, _clone
from .selectable import _interpret_as_from, _interpret_as_select, HasPrefixes
from .. import util
from .. import exc

class UpdateBase(HasPrefixes, Executable, ClauseElement):
    """Form the base for ``INSERT``, ``UPDATE``, and ``DELETE`` statements.

    """

    __visit_name__ = 'update_base'

    _execution_options = \
        Executable._execution_options.union({'autocommit': True})
    kwargs = util.immutabledict()
    _hints = util.immutabledict()
    _prefixes = ()

    def _process_colparams(self, parameters):
        def process_single(p):
            if isinstance(p, (list, tuple)):
                return dict(
                    (c.key, pval)
                    for c, pval in zip(self.table.c, p)
                )
            else:
                return p

        if isinstance(parameters, (list, tuple)) and \
              isinstance(parameters[0], (list, tuple, dict)):

            if not self._supports_multi_parameters:
                raise exc.InvalidRequestError(
                    "This construct does not support "
                    "multiple parameter sets.")

            return [process_single(p) for p in parameters], True
        else:
            return process_single(parameters), False

    def params(self, *arg, **kw):
        """Set the parameters for the statement.

        This method raises ``NotImplementedError`` on the base class,
        and is overridden by :class:`.ValuesBase` to provide the
        SET/VALUES clause of UPDATE and INSERT.

        """
        raise NotImplementedError(
            "params() is not supported for INSERT/UPDATE/DELETE statements."
            " To set the values for an INSERT or UPDATE statement, use"
            " stmt.values(**parameters).")

    def bind(self):
        """Return a 'bind' linked to this :class:`.UpdateBase`
        or a :class:`.Table` associated with it.

        """
        return self._bind or self.table.bind

    def _set_bind(self, bind):
        self._bind = bind
    bind = property(bind, _set_bind)

    @_generative
    def returning(self, *cols):
        """Add a RETURNING or equivalent clause to this statement.

        The given list of columns represent columns within the table that is
        the target of the INSERT, UPDATE, or DELETE. Each element can be any
        column expression. :class:`~sqlalchemy.schema.Table` objects will be
        expanded into their individual columns.

        Upon compilation, a RETURNING clause, or database equivalent,
        will be rendered within the statement.   For INSERT and UPDATE,
        the values are the newly inserted/updated values.  For DELETE,
        the values are those of the rows which were deleted.

        Upon execution, the values of the columns to be returned
        are made available via the result set and can be iterated
        using ``fetchone()`` and similar.   For DBAPIs which do not
        natively support returning values (i.e. cx_oracle),
        SQLAlchemy will approximate this behavior at the result level
        so that a reasonable amount of behavioral neutrality is
        provided.

        Note that not all databases/DBAPIs
        support RETURNING.   For those backends with no support,
        an exception is raised upon compilation and/or execution.
        For those who do support it, the functionality across backends
        varies greatly, including restrictions on executemany()
        and other statements which return multiple rows. Please
        read the documentation notes for the database in use in
        order to determine the availability of RETURNING.

        .. seealso::

          :meth:`.ValuesBase.return_defaults`

        """
        self._returning = cols


    @_generative
    def with_hint(self, text, selectable=None, dialect_name="*"):
        """Add a table hint for a single table to this
        INSERT/UPDATE/DELETE statement.

        .. note::

         :meth:`.UpdateBase.with_hint` currently applies only to
         Microsoft SQL Server.  For MySQL INSERT/UPDATE/DELETE hints, use
         :meth:`.UpdateBase.prefix_with`.

        The text of the hint is rendered in the appropriate
        location for the database backend in use, relative
        to the :class:`.Table` that is the subject of this
        statement, or optionally to that of the given
        :class:`.Table` passed as the ``selectable`` argument.

        The ``dialect_name`` option will limit the rendering of a particular
        hint to a particular backend. Such as, to add a hint
        that only takes effect for SQL Server::

            mytable.insert().with_hint("WITH (PAGLOCK)", dialect_name="mssql")

        .. versionadded:: 0.7.6

        :param text: Text of the hint.
        :param selectable: optional :class:`.Table` that specifies
         an element of the FROM clause within an UPDATE or DELETE
         to be the subject of the hint - applies only to certain backends.
        :param dialect_name: defaults to ``*``, if specified as the name
         of a particular dialect, will apply these hints only when
         that dialect is in use.
         """
        if selectable is None:
            selectable = self.table

        self._hints = self._hints.union(
                        {(selectable, dialect_name): text})


class ValuesBase(UpdateBase):
    """Supplies support for :meth:`.ValuesBase.values` to
    INSERT and UPDATE constructs."""

    __visit_name__ = 'values_base'

    _supports_multi_parameters = False
    _has_multi_parameters = False
    select = None

    def __init__(self, table, values, prefixes):
        self.table = _interpret_as_from(table)
        self.parameters, self._has_multi_parameters = \
                            self._process_colparams(values)
        if prefixes:
            self._setup_prefixes(prefixes)

    @_generative
    def values(self, *args, **kwargs):
        """specify a fixed VALUES clause for an INSERT statement, or the SET
        clause for an UPDATE.

        Note that the :class:`.Insert` and :class:`.Update` constructs support
        per-execution time formatting of the VALUES and/or SET clauses,
        based on the arguments passed to :meth:`.Connection.execute`.  However,
        the :meth:`.ValuesBase.values` method can be used to "fix" a particular
        set of parameters into the statement.

        Multiple calls to :meth:`.ValuesBase.values` will produce a new
        construct, each one with the parameter list modified to include
        the new parameters sent.  In the typical case of a single
        dictionary of parameters, the newly passed keys will replace
        the same keys in the previous construct.  In the case of a list-based
        "multiple values" construct, each new list of values is extended
        onto the existing list of values.

        :param \**kwargs: key value pairs representing the string key
          of a :class:`.Column` mapped to the value to be rendered into the
          VALUES or SET clause::

                users.insert().values(name="some name")

                users.update().where(users.c.id==5).values(name="some name")

        :param \*args: Alternatively, a dictionary, tuple or list
         of dictionaries or tuples can be passed as a single positional
         argument in order to form the VALUES or
         SET clause of the statement.  The single dictionary form
         works the same as the kwargs form::

            users.insert().values({"name": "some name"})

         If a tuple is passed, the tuple should contain the same number
         of columns as the target :class:`.Table`::

            users.insert().values((5, "some name"))

         The :class:`.Insert` construct also supports multiply-rendered VALUES
         construct, for those backends which support this SQL syntax
         (SQLite, Postgresql, MySQL).  This mode is indicated by passing a list
         of one or more dictionaries/tuples::

            users.insert().values([
                                {"name": "some name"},
                                {"name": "some other name"},
                                {"name": "yet another name"},
                            ])

         In the case of an :class:`.Update`
         construct, only the single dictionary/tuple form is accepted,
         else an exception is raised.  It is also an exception case to
         attempt to mix the single-/multiple- value styles together,
         either through multiple :meth:`.ValuesBase.values` calls
         or by sending a list + kwargs at the same time.

         .. note::

             Passing a multiple values list is *not* the same
             as passing a multiple values list to the :meth:`.Connection.execute`
             method.  Passing a list of parameter sets to :meth:`.ValuesBase.values`
             produces a construct of this form::

                INSERT INTO table (col1, col2, col3) VALUES
                                (col1_0, col2_0, col3_0),
                                (col1_1, col2_1, col3_1),
                                ...

             whereas a multiple list passed to :meth:`.Connection.execute`
             has the effect of using the DBAPI
             `executemany() <http://www.python.org/dev/peps/pep-0249/#id18>`_
             method, which provides a high-performance system of invoking
             a single-row INSERT statement many times against a series
             of parameter sets.   The "executemany" style is supported by
             all database backends, as it does not depend on a special SQL
             syntax.

         .. versionadded:: 0.8
             Support for multiple-VALUES INSERT statements.


        .. seealso::

            :ref:`inserts_and_updates` - SQL Expression
            Language Tutorial

            :func:`~.expression.insert` - produce an ``INSERT`` statement

            :func:`~.expression.update` - produce an ``UPDATE`` statement

        """
        if self.select is not None:
            raise exc.InvalidRequestError(
                        "This construct already inserts from a SELECT")
        if self._has_multi_parameters and kwargs:
            raise exc.InvalidRequestError(
                        "This construct already has multiple parameter sets.")

        if args:
            if len(args) > 1:
                raise exc.ArgumentError(
                            "Only a single dictionary/tuple or list of "
                            "dictionaries/tuples is accepted positionally.")
            v = args[0]
        else:
            v = {}

        if self.parameters is None:
            self.parameters, self._has_multi_parameters = \
                    self._process_colparams(v)
        else:
            if self._has_multi_parameters:
                self.parameters = list(self.parameters)
                p, self._has_multi_parameters = self._process_colparams(v)
                if not self._has_multi_parameters:
                    raise exc.ArgumentError(
                        "Can't mix single-values and multiple values "
                        "formats in one statement")

                self.parameters.extend(p)
            else:
                self.parameters = self.parameters.copy()
                p, self._has_multi_parameters = self._process_colparams(v)
                if self._has_multi_parameters:
                    raise exc.ArgumentError(
                        "Can't mix single-values and multiple values "
                        "formats in one statement")
                self.parameters.update(p)

        if kwargs:
            if self._has_multi_parameters:
                raise exc.ArgumentError(
                            "Can't pass kwargs and multiple parameter sets "
                            "simultaenously")
            else:
                self.parameters.update(kwargs)

    @_generative
    def return_defaults(self, *cols):
        """If available, make use of a RETURNING clause for the purpose
        of fetching server-side expressions and defaults.

        When used against a backend that supports RETURNING, all column
        values generated by SQL expression or server-side-default will be added
        to any existing RETURNING clause, excluding one that is specified
        by the :meth:`.UpdateBase.returning` method.   The column values
        will then be available on the result using the
        :meth:`.ResultProxy.server_returned_defaults` method as a
        dictionary, referring to values keyed to the :meth:`.Column` object
        as well as its ``.key``.

        This method differs from :meth:`.UpdateBase.returning` in these ways:

        1. It is compatible with any backend.  Backends that don't support
           RETURNING will skip the usage of the feature, rather than raising
           an exception.  The return value of :meth:`.ResultProxy.server_returned_defaults`
           will be ``None``

        2. It is compatible with the existing logic to fetch auto-generated
           primary key values, also known as "implicit returning".  Backends that
           support RETURNING will automatically make use of RETURNING in order
           to fetch the value of newly generated primary keys; while the
           :meth:`.UpdateBase.returning` method circumvents this behavior,
           :meth:`.UpdateBase.return_defaults` leaves it intact.

        3. :meth:`.UpdateBase.returning` leaves the cursor's rows ready for
           fetching using methods like :meth:`.ResultProxy.fetchone`, whereas
           :meth:`.ValuesBase.return_defaults` fetches the row internally.
           While all DBAPI backends observed so far seem to only support
           RETURNING with single-row executions,
           technically :meth:`.UpdateBase.returning` would support a backend
           that can deliver multiple RETURNING rows as well.  However
           :meth:`.ValuesBase.return_defaults` is single-row by definition.

        :param cols: optional list of column key names or :class:`.Column`
         objects.  If omitted, all column expressions evaulated on the server
         are added to the returning list.

        .. versionadded:: 0.9.0

        .. seealso::

            :meth:`.UpdateBase.returning`

            :meth:`.ResultProxy.returned_defaults`

        """
        self._return_defaults = cols or True


class Insert(ValuesBase):
    """Represent an INSERT construct.

    The :class:`.Insert` object is created using the
    :func:`~.expression.insert()` function.

    .. seealso::

        :ref:`coretutorial_insert_expressions`

    """
    __visit_name__ = 'insert'

    _supports_multi_parameters = True

    def __init__(self,
                table,
                values=None,
                inline=False,
                bind=None,
                prefixes=None,
                returning=None,
                return_defaults=False,
                **kwargs):
        ValuesBase.__init__(self, table, values, prefixes)
        self._bind = bind
        self.select = None
        self.inline = inline
        self._returning = returning
        self.kwargs = kwargs
        self._return_defaults = return_defaults

    def get_children(self, **kwargs):
        if self.select is not None:
            return self.select,
        else:
            return ()

    @_generative
    def from_select(self, names, select):
        """Return a new :class:`.Insert` construct which represents
        an ``INSERT...FROM SELECT`` statement.

        e.g.::

            sel = select([table1.c.a, table1.c.b]).where(table1.c.c > 5)
            ins = table2.insert().from_select(['a', 'b'], sel)

        :param names: a sequence of string column names or :class:`.Column`
         objects representing the target columns.
        :param select: a :func:`.select` construct, :class:`.FromClause`
         or other construct which resolves into a :class:`.FromClause`,
         such as an ORM :class:`.Query` object, etc.  The order of
         columns returned from this FROM clause should correspond to the
         order of columns sent as the ``names`` parameter;  while this
         is not checked before passing along to the database, the database
         would normally raise an exception if these column lists don't
         correspond.

        .. note::

           Depending on backend, it may be necessary for the :class:`.Insert`
           statement to be constructed using the ``inline=True`` flag; this
           flag will prevent the implicit usage of ``RETURNING`` when the
           ``INSERT`` statement is rendered, which isn't supported on a backend
           such as Oracle in conjunction with an ``INSERT..SELECT`` combination::

             sel = select([table1.c.a, table1.c.b]).where(table1.c.c > 5)
             ins = table2.insert(inline=True).from_select(['a', 'b'], sel)

        .. versionadded:: 0.8.3

        """
        if self.parameters:
            raise exc.InvalidRequestError(
                        "This construct already inserts value expressions")

        self.parameters, self._has_multi_parameters = \
                self._process_colparams(dict((n, Null()) for n in names))

        self.select = _interpret_as_select(select)

    def _copy_internals(self, clone=_clone, **kw):
        # TODO: coverage
        self.parameters = self.parameters.copy()
        if self.select is not None:
            self.select = _clone(self.select)


class Update(ValuesBase):
    """Represent an Update construct.

    The :class:`.Update` object is created using the :func:`update()` function.

    """
    __visit_name__ = 'update'

    def __init__(self,
                table,
                whereclause=None,
                values=None,
                inline=False,
                bind=None,
                prefixes=None,
                returning=None,
                return_defaults=False,
                **kwargs):
        ValuesBase.__init__(self, table, values, prefixes)
        self._bind = bind
        self._returning = returning
        if whereclause is not None:
            self._whereclause = _literal_as_text(whereclause)
        else:
            self._whereclause = None
        self.inline = inline
        self.kwargs = kwargs
        self._return_defaults = return_defaults


    def get_children(self, **kwargs):
        if self._whereclause is not None:
            return self._whereclause,
        else:
            return ()

    def _copy_internals(self, clone=_clone, **kw):
        # TODO: coverage
        self._whereclause = clone(self._whereclause, **kw)
        self.parameters = self.parameters.copy()

    @_generative
    def where(self, whereclause):
        """return a new update() construct with the given expression added to
        its WHERE clause, joined to the existing clause via AND, if any.

        """
        if self._whereclause is not None:
            self._whereclause = and_(self._whereclause,
                    _literal_as_text(whereclause))
        else:
            self._whereclause = _literal_as_text(whereclause)

    @property
    def _extra_froms(self):
        # TODO: this could be made memoized
        # if the memoization is reset on each generative call.
        froms = []
        seen = set([self.table])

        if self._whereclause is not None:
            for item in _from_objects(self._whereclause):
                if not seen.intersection(item._cloned_set):
                    froms.append(item)
                seen.update(item._cloned_set)

        return froms


class Delete(UpdateBase):
    """Represent a DELETE construct.

    The :class:`.Delete` object is created using the :func:`delete()` function.

    """

    __visit_name__ = 'delete'

    def __init__(self,
            table,
            whereclause=None,
            bind=None,
            returning=None,
            prefixes=None,
            **kwargs):
        """Construct :class:`.Delete` object.

        Similar functionality is available via the
        :meth:`~.TableClause.delete` method on
        :class:`~.schema.Table`.

        :param table: The table to be updated.

        :param whereclause: A :class:`.ClauseElement` describing the ``WHERE``
          condition of the ``UPDATE`` statement. Note that the
          :meth:`~Delete.where()` generative method may be used instead.

        .. seealso::

            :ref:`deletes` - SQL Expression Tutorial

        """
        self._bind = bind
        self.table = _interpret_as_from(table)
        self._returning = returning

        if prefixes:
            self._setup_prefixes(prefixes)

        if whereclause is not None:
            self._whereclause = _literal_as_text(whereclause)
        else:
            self._whereclause = None

        self.kwargs = kwargs

    def get_children(self, **kwargs):
        if self._whereclause is not None:
            return self._whereclause,
        else:
            return ()

    @_generative
    def where(self, whereclause):
        """Add the given WHERE clause to a newly returned delete construct."""

        if self._whereclause is not None:
            self._whereclause = and_(self._whereclause,
                    _literal_as_text(whereclause))
        else:
            self._whereclause = _literal_as_text(whereclause)

    def _copy_internals(self, clone=_clone, **kw):
        # TODO: coverage
        self._whereclause = clone(self._whereclause, **kw)
