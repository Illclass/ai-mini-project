import {recommendationEntries} from './recommendations.js'
export function suggestedQuestions(context){return recommendationEntries(context).map(entry=>entry.q)}
