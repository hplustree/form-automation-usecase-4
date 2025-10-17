
import React from 'react';
import {
  FormGroup,
  FormControlLabel,
  Checkbox,
  Typography,
  Paper,
} from '@mui/material';

const KeyPointSelector = ({ availableKeyPoints, selectedKeyPoints, onKeyPointsChange }) => {

  const handleCheckboxChange = (event) => {
    const { name, checked } = event.target;
    let newSelection;
    if (checked) {
      newSelection = [...selectedKeyPoints, name];
    } else {
      newSelection = selectedKeyPoints.filter((key) => key !== name);
    }
    onKeyPointsChange(newSelection);
  };

  return (
    <Paper elevation={3} sx={{ p: 3, mt: 3 }}>
      <Typography variant="h6" gutterBottom>
        Select Key Points for Extraction
      </Typography>
      <FormGroup>
        {availableKeyPoints.map((keyPoint) => (
          <FormControlLabel
            key={keyPoint}
            control={
              <Checkbox
                checked={selectedKeyPoints.includes(keyPoint)}
                onChange={handleCheckboxChange}
                name={keyPoint}
              />
            }
            label={keyPoint}
          />
        ))}
      </FormGroup>
    </Paper>
  );
};

export default KeyPointSelector;