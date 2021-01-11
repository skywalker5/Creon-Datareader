def score_sequence_span_level(predicted_labels, gold_labels):
    if len(predicted_labels) != len(gold_labels):
        raise ValueError("Lengths of predicted_labels and gold_labels must match")

    tp, fp, fn = 0, 0, 0
    # Collects predicted and correct spans for the instance
    predicted_spans, correct_spans = set(), set()
    data = ((predicted_labels, predicted_spans), (gold_labels, correct_spans))
    for labels, spans in data:
        start = None
        tag = None
        for i in range(len(labels)):
            if labels[i][0] == 'I':
                # Two separate conditional statements so that 'I' is always
                # recognized as a valid label
                if start is None:
                    start = i
                    tag = labels[i]
                # Also checks if label has switched to new type
                elif tag != labels[i]:
                    spans.add((start, i, tag))
                    start = i
                    tag = labels[i]
            elif labels[i][0] == 'O' or labels[i] == 'ABS':
                if start is not None:
                    spans.add((start, i, tag))
                start = None
                tag = None
            elif labels[i][0] == 'B':
                if start is not None:
                    spans.add((start, i, tag))
                start = i
                tag = labels[i]
            else:
                raise ValueError("Unrecognized label: %s" % labels[i] )

        # Closes span if still active
        if start is not None:
            spans.add((start, len(labels), tag))

    # Compares predicted spans with correct spans
    for span in correct_spans:
        if span in predicted_spans:
            tp += 1
            predicted_spans.remove(span)
        else:
            fn += 1
    fp += len(predicted_spans)

    return tp, fp, fn

predicted_labels=['B-Org','O','O','O','O','O','O','B-Loc','I-Loc']
gold_labels = ['B-Org','O','B-Prod','I-Prod','O','O','O','B-Loc','I-Loc']
score_sequence_span_level(predicted_labels, gold_labels)