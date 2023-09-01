"""
This package automates MESH model setup through a flexible workflow that can
be set up using a JSON configuration file, a Command Line Interface (CLI) or
directly inside a Python script/environment.

Much of the work has been adopted from workflows developed by Dr. Ala Bahrami
and Cooper Albano at the University of Saskatchewan applying MESH modelling
framework to the North American domain.
"""

import pandas as pd
import geopandas as gpd
import pint

from typing import (
    Dict,
    Sequence,
    Union,
)

import re
import json
import glob
import os

from ._default_dicts import (
    ddb_global_attrs_default,
    ddb_local_attrs_default,
)
from meshflow import utility


class MESHWorkflow(object):
    """
    Main Workflow class of MESH


    Attributes
    ----------


    Parameters
    ----------


    """
    # main constructor
    def __init__(
        self,
        riv: str,
        cat: str,
        landcover: str,
        forcing_files: str,
        forcing_vars: Sequence[str],
        main_id: str,
        ds_main_id: str,
        forcing_units: Dict[str, str] = None,  # pint standards
        forcing_to_units: Dict[str, str] = None,
        outlet_value: int = -9999,
        riv_cols: Dict[str, Union[str, int]] = None,
        cat_cols: Dict[str, Union[str, int]] = None,
        ddb_vars: Dict[str, str] = None,
        ddb_local_attrs: Dict[str, str] = None,
        ddb_global_attrs: Dict[str, str] = None,
        ddb_min_values: Dict[str, float] = None,
    ) -> None:
        """Main constructor of MESHWorkflow
        """
        # forcing variables
        if not forcing_vars:
            raise ValueError("`forcing_vars` cannot be empty")

        # check dictionary dtypes
        for item in [forcing_units, forcing_to_units]:
            if not isinstance(item, dict) and (item is not None):
                raise TypeError(f"`{item}` must be of type dict")

        # if ddb_local_attrs not assigned
        if not ddb_global_attrs:
            self.ddb_global_attrs = ddb_global_attrs_default
        else:
            self.ddb_global_attrs = ddb_global_attrs

        # if ddb_local_attrs not assigned
        if not ddb_local_attrs:
            self.ddb_local_attrs = ddb_local_attrs_default
        else:
            self.ddb_local_attrs = ddb_local_attrs

        # assigning variables to be "lazy loaded" later
        self._riv_path = riv
        self._cat_path = cat
        self._landcover_path = landcover

        # assgining forcing files path to be "lazy loaded" later
        self._forcing_path = forcing_files

        # assign inputs
        self.main_id = main_id
        self.ds_main_id = ds_main_id
        self.forcing_vars = forcing_vars
        self.forcing_units = forcing_units
        self.forcing_to_units = forcing_to_units
        self.outlet_value = outlet_value
        self.riv_cols = riv_cols
        self.cat_cols = cat_cols
        self.ddb_vars = ddb_vars
        self.ddb_min_values = ddb_min_values

        # assing inputs read from files
        self._read_input_files()

    def _read_input_files(self):
        """Read necessary input files
        [FIXME]: lazy loading may be necessary in the future to save time
        when istantiating from MESHWorkflow class
        [FIXME]: eventually, this needs to turn into its own object,
        rather than reading a simple file in pandas DataFrame format
        """
        self.riv = gpd.read_file(self._riv_path)
        self.cat = gpd.read_file(self._cat_path)
        self.landcover = self._read_landcover()

    def _read_landcover(self):
        """
        Return landcover object for elements given in the input domain for
        MESH model setup
        """

        # [FIXME]: This needs to be flexible in future versions
        _lc_prefix = 'frac_'

        # local _seg_ids and _ds_seg_ids
        _seg_ids = self.cat.loc[:, self.main_id]

        # read the landcover data as a pandas.DataFrame
        _lc_df = pd.read_csv(self._landcover_path,
                             index_col=0,
                             header=0)

        # select rows and columns to be included for landcover object
        _rows = [row for row in _lc_df.index if _seg_ids.isin([row]).any()]
        _cols = [col for col in _lc_df.columns if
                 col.startswith(_lc_prefix)]

        # return a copy of the dataframe including hrus available in the
        # input domain and only fractions

        return _lc_df.loc[_rows, _cols].copy()

    @property
    def coords(self):
        # calculate centroid latitude and longitude values
        return utility.extract_centroid(gdf=self.cat,
                                        obj_id=self.main_id)

    @property
    def forcing_files(self):
        pattern = r"\.nc\*?|\.nc"
        if re.search(pattern, self._forcing_path):
            if glob.glob(self._forcing_path):
                return self._forcing_path
        else:
            _path = os.path.join(self._forcing_path, '*.nc*')
            if glob.glob(_path):
                return _path

    @classmethod
    def from_dict(
        cls: 'MESHWorkflow',
        init_dict: Dict = {},
    ) -> 'MESHWorkflow':
        """
        Constructor to use a dictionary to instantiate
        """
        if len(init_dict) == 0:
            raise KeyError("`init_dict` cannot be empty")
        assert isinstance(init_dict, dict), "`init_dict` must be a `dict`"

        return cls(**init_dict)

    @classmethod
    def from_json(
        cls: 'MESHWorkflow',
        json_str: str,
    ) -> 'MESHWorkflow':
        """
        Constructor to use a loaded JSON string
        """
        # building customized MESHWorkflow's JSON string decoder object
        decoder = json.JSONDecoder(object_hook=MESHWorkflow._json_decoder)
        json_dict = decoder.decode(json_str)
        # return class instance
        return cls.from_dict(json_dict)

    @classmethod
    def from_json_file(
        cls: 'MESHWorkflow',
        json_file: 'str',
    ) -> 'MESHWorkflow':
        """
        Constructor to use a JSON file path
        """
        with open(json_file) as f:
            json_dict = json.load(f,
                                  object_hook=MESHWorkflow._easymore_decoder)

        return cls.from_dict(json_dict)

    @staticmethod
    def _env_var_decoder(s):
        """
        OS environmental variable decoder
        """
        # RE patterns
        env_pat = r'\$(.*?)/'
        bef_pat = r'(.*?)\$.*?/?'
        aft_pat = r'\$.*?(/.*)'
        # strings after re matches
        e = re.search(env_pat, s).group(1)
        b = re.search(bef_pat, s).group(1)
        a = re.search(aft_pat, s).group(1)
        # extract environmental variable
        v = os.getenv(e)
        # return full: before+env_var+after
        if v:
            return b+v+a
        return s

    @staticmethod
    def _json_decoder(obj):
        """
        Decoding typical JSON strings returned into valid Python objects
        """
        if obj in ["true", "True", "TRUE"]:
            return True
        elif obj in ["false", "False", "FALSE"]:
            return False
        elif isinstance(obj, str):
            if '$' in obj:
                return MESHWorkflow._env_var_decoder(obj)
        elif isinstance(obj, dict):
            return {k: MESHWorkflow._json_decoder(v) for k, v in obj.items()}
        return obj

    def run(self):
        """
        Run the workflow and prepare a MESH setup
        """
        # MESH specific variable names in ddb
        _rank_var = 'Rank'
        _next_var = 'Next'
        _gru_name = 'gru'

        # initialize MESH-specific variables including `rank` and `next`
        # and the re-ordered `main_seg` and `ds_main_seg`;
        # This will assign: 1) self.rank, 2) self.next, 3) self.main_seg,
        # and 4) self.ds_main_seg
        self._init_idx_vars()

        # reorder river segments and add rank and next to the
        # geopandas.DataFrame object
        self.reordered_riv = self._reorder_riv(rank_name=_rank_var,
                                               next_name=_next_var)

        # defined ordered_dims variables
        _ordered_dims = {self.main_id: self.main_seg}

        # 1 generate drainage database
        self.ddb = utility.prepare_mesh_ddb(riv=self.reordered_riv,
                                            cat=self.cat,
                                            landcover=self.landcover,
                                            coords=self.coords,
                                            cat_dim=self.main_id,
                                            gru_dim=_gru_name,
                                            include_vars=self.ddb_vars,
                                            attr_local=self.ddb_local_attrs,
                                            attr_global=self.ddb_global_attrs,
                                            min_values=self.ddb_min_values,
                                            fill_na=None,
                                            ordered_dims=_ordered_dims)

        # forcing unit registry
        _ureg = pint.UnitRegistry(force_ndarray_like=True)
        _ureg.define('millibar = 1e-3 * bar')

        # 2 generate forcing data
        # making a list of variables
        self.forcing = utility.forcing_prep.mesh_forcing(
                            path=self.forcing_files,
                            variables=self.forcing_vars,
                            units=self.forcing_units,
                            to_units=self.forcing_to_units,
                            unit_registry=_ureg)

        # 3 generate land-cover dependant setting files for MESH

        # 4 generate other setting files for MESH

        return

    def save(self, output_dir):
        """Save the drainage databse, and forcing files to output_dir path

        Parameters
        ----------

        Returns
        -------
        """
        # MESH specific variable names
        ddb_file = 'MESH_drainage_database.nc'
        forcing_file = 'MESH_forcing.nc'

        # printing drainage database netcdf file
        self.ddb.to_netcdf(os.path.join(output_dir, ddb_file))

        # printin forcing netcdf file
        self.forcing.to_netcdf(os.path.join(output_dir, forcing_file))

        return

    def _init_idx_vars(self):
        """
        Initiating MESH variables such as `rank`, `next`, `main_seg`, and
        `ds_main_seg`
        """
        # extracting pandas.Series for river segments and their downstream
        # segments from the `self.riv` geopandas.geoDataFrame
        _seg = self.riv.loc[:, self.main_id]
        _ds_seg = self.riv.loc[:, self.ds_main_id]

        # assigning modified "index" variables compatible with MESH
        # requirements

        # building a dictionary as an input to `extract_rank_next`
        # function
        _kwargs = {
            'seg': _seg,
            'ds_seg': _ds_seg,
            'outlet_value': self.outlet_value,
        }

        # calling `extract_rank_next` function
        (self.rank,
         self.next,
         self.main_seg,
         self.ds_main_seg) = utility.extract_rank_next(**_kwargs)

        return

    def _reorder_riv(
        self,
        rank_name='rank',
        next_name='next'
    ) -> gpd.GeoDataFrame:

        # necessary values
        _cols = [rank_name, next_name, self.main_id]
        _data = [self.rank, self.next, self.main_seg]

        # pandas.DataFrame of `_cols` and `_data`
        _idx_df = pd.DataFrame({col: datum
                                for col, datum in
                                zip(_cols, _data)})

        # re-ordered view of `self.riv` based on the `self.main_seg`
        # that are ordered based on `self.rank`
        _riv_reindexed = self.riv.set_index(self.main_id).copy()

        # getting a copy of `self.riv` with the new order of
        # `self.main_seg`
        _riv_reordered = _riv_reindexed.loc[self.main_seg].reset_index().copy()

        # reordered elements
        _reordered_riv = gpd.GeoDataFrame(pd.merge(left=_riv_reordered,
                                                   right=_idx_df,
                                                   on=self.main_id)
                                          )

        return _reordered_riv

    def _progress_bar():
        return

    def _submit_job():
        pass
