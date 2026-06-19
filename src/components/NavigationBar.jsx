import React, { useState } from "react";
import { Link } from "wouter";
import SearchIcon from "@mui/icons-material/Search";
import SettingsIcon from "@mui/icons-material/Settings";
import VolumeUpIcon from "@mui/icons-material/VolumeUp";
import { IconButton } from "@mui/material";
import { useAdmin } from "hooks/admin";
import { useConfig } from "hooks/config";
import { useVolume } from "hooks/volume";
import VolumeKnob from "components/playback/VolumeKnob";

const NavigationBar = () => {
  const { isAdmin, triggerSecretAdminAction } = useAdmin();
  const { config } = useConfig();
  const { volumeEnabled } = useVolume();
  const siteTitle = config?.siteTitle ?? "pibox";
  const [showVolume, setShowVolume] = useState(false);

  return (
    <>
      <ul className="flex justify-between items-center list-none m-0 px-2">
        <li>
          {!isAdmin ? (
            <h2
              className="text-start inline-block font-bold text-xl pl-2"
              onClick={triggerSecretAdminAction}
            >
              {siteTitle}
            </h2>
          ) : (
            <Link className="Link" to="/session">
              <IconButton color="secondary">
                <SettingsIcon fontSize="large" />
              </IconButton>
            </Link>
          )}
        </li>
        <li className="flex items-center gap-1">
          {volumeEnabled && (
            <IconButton color="secondary" onClick={() => setShowVolume(true)}>
              <VolumeUpIcon fontSize="large" />
            </IconButton>
          )}
          <Link className="Link" to="/search">
            <IconButton color="secondary">
              <SearchIcon fontSize="large" />
            </IconButton>
          </Link>
        </li>
      </ul>
      {showVolume && <VolumeKnob onClose={() => setShowVolume(false)} />}
    </>
  );
};

export default NavigationBar;
