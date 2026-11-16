import { marketWords, type MarketWord } from './marketWords'

interface Props {
  words: readonly MarketWord[]
  title?: string
}

/** Native details keeps jargon behind an optional, keyboard-accessible explanation. */
export default function BeginnerHelp({ words, title = 'What do these words mean?' }: Props) {
  return <details className="rounded-lg border border-slate-700 bg-slate-950/60 p-4 text-sm text-slate-300">
    <summary className="cursor-pointer font-semibold text-emerald-300">{title}</summary>
    <dl className="mt-3 space-y-3">
      {words.map(word => <div key={word}>
        <dt className="font-semibold text-slate-100">{marketWords[word].label}</dt>
        <dd className="mt-1 leading-relaxed">{marketWords[word].explanation}</dd>
      </div>)}
    </dl>
  </details>
}
