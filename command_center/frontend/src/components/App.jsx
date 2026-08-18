import React, { useState } from 'react';
import { Box, Container, Typography, CssBaseline } from '@mui/material';
import QueryForm from './QueryForm';
import ResultsPanel from './ResultsPanel';

const App = () => {
    const [results, setResults] = useState(null);
    const [isLoading, setIsLoading] = useState(false);

    const handleQuerySubmit = async (queryData) => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/query', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(queryData),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            setResults(data);
        } catch (error) {
            console.error('Error fetching query results:', error);
            setResults({
                answers: [],
                error: error.message,
            });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <>
            <CssBaseline />
            <Container maxWidth="lg">
                <Box sx={{ my: 4 }}>
                    <Typography variant="h3" component="h1" gutterBottom align="center">
                        KURUKSHETRA Command Center
                    </Typography>
                    <Typography variant="h5" component="h2" gutterBottom align="center" color="text.secondary">
                        SPM Document Query Interface
                    </Typography>

                    <Box sx={{ mt: 6, mb: 4 }}>
                        <QueryForm onSubmit={handleQuerySubmit} isLoading={isLoading} />
                    </Box>

                    {results && (
                        <ResultsPanel results={results} />
                    )}
                </Box>
            </Container>
        </>
    );
};

export default App;