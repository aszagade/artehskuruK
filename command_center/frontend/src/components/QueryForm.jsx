import React from 'react';
import { Box, TextField, Button, MenuItem, Typography } from '@mui/material';

const QueryForm = ({ onSubmit, isLoading }) => {
    const [query, setQuery] = React.useState('');
    const [teamId, setTeamId] = React.useState('spm-team');
    const [confidenceThreshold, setConfidenceThreshold] = React.useState(5);
    const [maxResults, setMaxResults] = React.useState(10);

    const handleSubmit = (e) => {
        e.preventDefault();
        onSubmit({
            query,
            team_id: teamId,
            confidence_threshold: confidenceThreshold,
            max_results: maxResults,
        });
    };

    return (
        <Box component="form" onSubmit={handleSubmit} sx={{ display: 'flex', flexDirection: { xs: 'column', sm: 'row' }, gap: 2, alignItems: { xs: 'stretch', sm: 'end' } }}>
            <TextField
                fullWidth
                label="Enter your query"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="How to handle G3 RMS decision upload failures?"
                variant="outlined"
                size="medium"
                sx={{ flexGrow: 1 }}
            />

            <TextField
                select
                label="Team"
                value={teamId}
                onChange={(e) => setTeamId(e.target.value)}
                variant="outlined"
                size="medium"
                sx={{ minWidth: 150 }}
            >
                <MenuItem value="spm-team">SPM Team</MenuItem>
            </TextField>

            <TextField
                select
                label="Confidence Threshold"
                value={confidenceThreshold}
                onChange={(e) => setConfidenceThreshold(Number(e.target.value))}
                variant="outlined"
                size="medium"
                sx={{ minWidth: 150 }}
            >
                <MenuItem value={3}>Low (3)</MenuItem>
                <MenuItem value={5}>Medium (5)</MenuItem>
                <MenuItem value={7}>High (7)</MenuItem>
            </TextField>

            <TextField
                select
                label="Max Results"
                value={maxResults}
                onChange={(e) => setMaxResults(Number(e.target.value))}
                variant="outlined"
                size="medium"
                sx={{ minWidth: 120 }}
            >
                <MenuItem value={5}>5</MenuItem>
                <MenuItem value={10}>10</MenuItem>
                <MenuItem value={20}>20</MenuItem>
            </TextField>

            <Button
                type="submit"
                variant="contained"
                size="large"
                disabled={isLoading || !query.trim()}
                sx={{ py: 1.5, px: 4 }}
            >
                {isLoading ? 'Searching...' : 'Search Documents'}
            </Button>
        </Box>
    );
};

export default QueryForm;