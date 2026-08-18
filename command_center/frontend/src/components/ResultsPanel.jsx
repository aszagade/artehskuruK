import React from 'react';
import { Box, Typography, Paper, List, ListItem, ListItemText, Divider, Chip, Alert } from '@mui/material';

const ResultsPanel = ({ results }) => {
    if (results.error) {
        return (
            <Alert severity="error" sx={{ mt: 2 }}>
                Error: {results.error}
            </Alert>
        );
    }

    if (!results.answers || results.answers.length === 0) {
        return (
            <Alert severity="info" sx={{ mt: 2 }}>
                No answers found for your query.
            </Alert>
        );
    }

    return (
        <Box sx={{ mt: 4 }}>
            <Typography variant="h5" gutterBottom>
                Query Results ({results.answers.length} answer(s))
            </Typography>

            {results.confidence_level && (
                <Box sx={{ mb: 2 }}>
                    <Chip
                        label={
                            `Confidence: ${results.confidence_level} (${results.confidence_description})`
                        }
                        color={results.confidence_level >= 7 ? 'success' : results.confidence_level >= 5 ? 'primary' : 'warning'}
                    />
                </Box>
            )}

            <List sx={{ width: '100%' }}>
                {results.answers.map((answer, index) => (
                    <React.Fragment key={index}>
                        <ListItem alignItems="flex-start">
                            <Paper elevation={2} sx={{ p: 3, mb: 2, width: '100%' }}>
                                <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
                                    <Typography variant="subtitle2" color="text.secondary">
                                        Document: {answer.document_id || 'Unknown'}
                                    </Typography>
                                    {answer.confidence && (
                                        <Chip
                                            label={`Confidence: ${answer.confidence}`}
                                            size="small"
                                            color={answer.confidence >= 7 ? 'success' : answer.confidence >= 5 ? 'primary' : 'warning'}
                                        />
                                    )}
                                </Box>

                                <Typography variant="body1" paragraph>
                                    {answer.answer}
                                </Typography>

                                {answer.context && answer.context.length > 0 && (
                                    <Box mt={2}>
                                        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                            Context:
                                        </Typography>
                                        {answer.context.map((ctx, ctxIndex) => (
                                            <Typography key={ctxIndex} variant="caption" component="div" sx={{ pl: 2 }}>
                                                • {ctx}
                                            </Typography>
                                        ))}
                                    </Box>
                                )}
                            </Paper>
                        </ListItem>
                        {index < results.answers.length - 1 && <Divider component="li" />}
                    </React.Fragment>
                ))}
            </List>
        </Box>
    );
};

export default ResultsPanel;