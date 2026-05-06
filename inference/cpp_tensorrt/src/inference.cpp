#include "inference.hpp"

#include <algorithm>
#include <stdexcept>

CameraTensorRTInfer::CameraTensorRTInfer(
    const std::string& engine_path,
    const std::string& config_path,
    const std::string& roi_config_path,
    bool prestart_mode,
    bool settle_single_frame
)
    : prestart_mode_(prestart_mode),
      settle_single_frame_(settle_single_frame) {
    int enter_frames = 3;
    int exit_frames = 5;

    bool ok = LoadSafetyConfig(
        config_path,
        roi_config_path,
        inference_config_,
        roi_rules_,
        enter_frames,
        exit_frames
    );

    if (!ok) {
        throw std::runtime_error("Failed to load ROI/alarm config");
    }

    detector_ = std::make_unique<TrtDetector>(engine_path);
    detector_->MakePipe(true);

    roi_manager_ = std::make_unique<ROIManager>(roi_rules_);

    alarm_logic_ = std::make_unique<AlarmLogic>(
        roi_rules_,
        enter_frames,
        exit_frames
    );
}

cv::Mat CameraTensorRTInfer::Infer(const cv::Mat& input_img) {
    if (input_img.empty()) {
        throw std::runtime_error("Input image is empty");
    }

    cv::Mat frame = input_img.clone();

    detector_->CopyFromMat(frame, inference_config_.input_size);

    auto begin = std::chrono::steady_clock::now();

    detector_->Infer();

    auto end = std::chrono::steady_clock::now();

    std::vector<Detection> detections;
    detector_->PostProcess(detections, inference_config_);

    auto detection_with_roi = roi_manager_->Apply(
        detections,
        frame.size()
    );

    FrameResult frame_result;

    int eval_times = 1;

    if (settle_single_frame_) {
        eval_times = std::max(
            alarm_logic_->enter_frames(),
            alarm_logic_->exit_frames()
        );
    }

    for (int i = 0; i < eval_times; ++i) {
        frame_result = alarm_logic_->Evaluate(
            detection_with_roi,
            prestart_mode_
        );
    }

    DrawResult(frame, frame_result, begin, end);

    return frame;
}

void CameraTensorRTInfer::DrawResult(
    cv::Mat& frame,
    const FrameResult& frame_result,
    const std::chrono::steady_clock::time_point& begin,
    const std::chrono::steady_clock::time_point& end
) {
    roi_manager_->DrawROIs(frame);

    std::vector<Detection> plain_detections;
    plain_detections.reserve(frame_result.detections.size());

    for (const auto& item : frame_result.detections) {
        plain_detections.push_back(item.detection);
    }

    detector_->DrawDetections(frame, plain_detections);

    float millis =
        static_cast<float>(
            std::chrono::duration_cast<std::chrono::milliseconds>(
                end - begin
            ).count()
        );

    if (millis > 0.0f) {
        cv::putText(
            frame,
            cv::format("FPS %.2f", 1000.0f / millis),
            cv::Point(10, 20),
            cv::FONT_HERSHEY_SIMPLEX,
            0.6,
            cv::Scalar(0, 0, 255),
            2
        );
    }

    cv::putText(
        frame,
        cv::format(
            "state=%s start=%s alarm=%s",
            SystemStateToString(frame_result.system_state),
            frame_result.allow_start ? "true" : "false",
            frame_result.alarm ? "true" : "false"
        ),
        cv::Point(10, 45),
        cv::FONT_HERSHEY_SIMPLEX,
        0.6,
        frame_result.alarm ? cv::Scalar(0, 0, 255)
                           : cv::Scalar(0, 255, 0),
        2
    );
}