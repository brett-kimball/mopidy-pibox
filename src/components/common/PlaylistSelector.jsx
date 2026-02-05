import React from "react";
import {
  FormControl,
  Checkbox,
  Autocomplete,
  TextField,
} from "@mui/material";
import CheckBoxOutlineBlankIcon from "@mui/icons-material/CheckBoxOutlineBlank";
import CheckBoxIcon from "@mui/icons-material/CheckBox";

/**
 * A reusable playlist/mix selector component.
 * Used on both the NewSessionPage and SessionPage for selecting playlists.
 */
const PlaylistSelector = ({
  availablePlaylists,
  selectedPlaylists,
  onChange,
  label = "Playlists",
  disabled = false,
}) => {
  return (
    <FormControl fullWidth>
      <Autocomplete
        multiple
        disableCloseOnSelect
        disabled={disabled}
        options={availablePlaylists}
        sx={{
          margin: 0,
          width: "100%",
        }}
        getOptionLabel={(playlist) => playlist.name}
        isOptionEqualToValue={(option, value) => option.uri === value.uri}
        style={{ width: "100%" }}
        renderInput={(params) => (
          <TextField {...params} label={label} variant="outlined" />
        )}
        renderOption={(props, option, { selected }) => {
          const { key, ...optionProps } = props;
          return (
            <li key={key} {...optionProps}>
              <Checkbox
                icon={<CheckBoxOutlineBlankIcon fontSize="small" />}
                checkedIcon={<CheckBoxIcon fontSize="small" />}
                style={{ marginRight: 8 }}
                checked={selected}
              />
              {option.name}
            </li>
          );
        }}
        value={selectedPlaylists}
        onChange={(_event, value) => onChange(value)}
      />
    </FormControl>
  );
};

export default PlaylistSelector;
