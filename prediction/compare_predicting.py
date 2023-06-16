import sys
from predicting import get_match_by_id, generate_prediction
from processing import predict_played_match


def compare_predictions(hltv_id):
    unplayed_match = get_match_by_id(hltv_id)
    map_infos = None
    if "mapInfos" in unplayed_match:
        map_infos = unplayed_match["mapInfos"]
    u_pred = generate_prediction(unplayed_match, map_infos, ignore_cache=True)

    p_pred = predict_played_match(hltv_id)

    print("Unplayed prediction", u_pred)
    print("Played prediction", p_pred)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        hltv_id = sys.argv[1]
        compare_predictions(hltv_id)
