"""
Database module.

All variables and config options that are only configurable through
Discord commands are stored in this database. For configuration files
that are meant to be modifyable are stored as YAMLs and managed
separately.

The database library used here is sqlitedict, no particular reason for
using it.
"""

from typing import Union, List, Optional

from sqlitedict import SqliteDict

from ophelia import settings


DBTypes = Union[int, str, bool, dict]
RawKeyType = Union[str, tuple]


class OpheliaDatabase:
    """Database class for the Ophelia bot."""

    __slots__ = ["db", "file_path", "autocommit"]

    def __init__(self, file_path: str, autocommit: bool = True) -> None:
        """
        Initializer for the OpheliaDatabase class.

        :param file_path: Path to database file
        :param autocommit: Whether to commit all changes to the database
            file automatically
        """
        self.file_path = file_path
        self.autocommit = autocommit
        self.db = SqliteDict(file_path, autocommit=autocommit)

    def traverse_single(
            self,
            key: str,
            delete: bool = False,
            value: Optional[DBTypes] = None,
            default: Optional[DBTypes] = None
    ) -> DBTypes:
        """
        Traverse the database on the first layer to insert, delete, or
        retrieve values.

        :param key: Key to value
        :param delete: Whether to delete value stored at key
        :param value: New value to update the database with, or None
            if the user does not want to update the database
        :param default: Default value to return if no value was found
        :return: Value stored at or newly inserted into key, or the
            value that was most recently removed at key
        :raises KeyError: When the given key does not exist when
            retrieving and there was no default provided
        """
        if delete:
            deleted_item = self.db.pop(key)
            return deleted_item

        if value is None:
            if default is None:
                return self.db[key]
            return self.db.setdefault(key, default)

        self.db[key] = value
        return value

    def traverse(
            self,
            path: List[str],
            delete: bool = False,
            create_new: bool = True,
            value: Optional[DBTypes] = None,
            default: Optional[DBTypes] = None
    ) -> DBTypes:
        """
        Traverse the database to insert, delete, or retrieve values.

        :param path: Path to value in nested dictionary
        :param delete: Whether to delete the value stored at path
        :param create_new: Create new nested dictionaries if the given
            sub-path does not exist
        :param value: New value to update the database with, or None if
            the user does not want to update the database
        :param default: Default value to return if no value was found
        :return: Value stored at or newly inserted into path, or the
            value that was most recently removed
        :raises KeyError: When given path does not exist or is invalid
        """
        if len(path) == 0:
            raise KeyError

        # Special case: when path only has one key (This special case
        # is necessary since under the hood, the database only has one
        # layer of data and everything else is just kept in a blob,
        # which makes the first layer in the nested structure extra
        # special)
        main_key = path[0]
        if len(path) == 1:
            return self.traverse_single(
                key=main_key,
                delete=delete,
                value=value,
                default=default
            )

        # Dissect dict path
        main_dict = self.db.get(main_key, {})
        curr_working_dict = main_dict
        sub_path = path[1:-1]
        last_key = path[-1]

        # Traverse dictionary
        for key in sub_path:
            if create_new:
                curr_working_dict = curr_working_dict.setdefault(key, {})
            else:
                curr_working_dict = curr_working_dict[key]

        # Deleting a value
        if delete:
            deleted_item = curr_working_dict.pop(last_key)
            self.db[main_key] = main_dict
            return deleted_item

        # Retrieving a value
        if value is None:
            if default is None:
                return curr_working_dict[last_key]

            return_value = curr_working_dict.setdefault(last_key, default)
            self.db[main_key] = main_dict
            return return_value

        # Setting a value
        curr_working_dict[last_key] = value
        self.db[main_key] = main_dict
        return value

    @staticmethod
    def to_list(key: RawKeyType) -> List[str]:
        """
        Converts raw key type (string or tuple) into the required list
        of strings.

        :param key: Raw key path
        :return: Key path expressed as a string list
        """
        if not isinstance(key, tuple):
            return [str(key)]

        return list(key)

    def __setitem__(self, key: RawKeyType, value: DBTypes) -> None:
        """
        Insert database entry.

        For instance:
        db["key", "sub_key"] = value

        :param key: Path to entry in nested database
        :param value: New value
        """
        self.traverse(path=self.to_list(key), value=value)

    def __getitem__(self, key: RawKeyType) -> DBTypes:
        """
        Retrieve database entry.

        :param key: Path to entry in nested database
        :return: Value at path
        :raises KeyError: When key path is invalid
        """
        return self.traverse(path=self.to_list(key), create_new=False)

    def setdefault(self, key: RawKeyType, default: DBTypes) -> DBTypes:
        """
        Retrieve database entry with default.

        :param key: Path to entry in nested database
        :param default: Default value to set if database does not
            contain value
        :return: Value at path
        """
        return self.traverse(
            path=self.to_list(key),
            create_new=True,
            default=default
        )

    def __delitem__(self, key: RawKeyType) -> None:
        """
        Delete database entry.
        :param key: Path to entry in nested database
        """
        self.traverse(path=self.to_list(key), delete=True, create_new=False)

    def commit(self) -> None:
        """Commit changes if autocommit is not turned on."""
        if not self.autocommit:
            self.db.commit()


db = OpheliaDatabase(settings.file_path_db, autocommit=True)
