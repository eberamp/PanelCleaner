from PIL import Image
from logzero import logger

import pcleaner.image_ops as ops
import pcleaner.structures as st


def denoise_page(d_data: st.DenoiserData) -> st.DenoiseAnalytic:
    """
    Load the MaskData from the json file and perform the denoising process.

    :param d_data: All the data needed for the denoising process.
    :return: Analytics.
    """

    # Load all the cached data.
    mask_data = st.MaskData.from_json(d_data.json_path.read_text())
    cleaned_image = Image.open(mask_data.cleaned_path)
    mask_image = Image.open(mask_data.mask_path)

    # Alias.
    d_conf = d_data.denoiser_config
    c_conf = d_data.cleaner_config

    # Filter for the min deviation to consider for denoising.
    boxes_to_denoise: list[tuple[int, int, int, int]] = [
        box
        for box, deviation in mask_data.boxes_with_deviation
        if deviation > d_conf.noise_min_standard_deviation
    ]

    noise_masks_with_coords: list[tuple[Image.Image, tuple[int, int]]] = [
        ops.generate_noise_mask(cleaned_image, mask_image, box, d_conf) for box in boxes_to_denoise
    ]

    combined_noise_mask = ops.combine_noise_masks(cleaned_image.size, noise_masks_with_coords)
    cleaned_image.paste(combined_noise_mask, (0, 0), combined_noise_mask)

    # Debug save.
    if d_data.show_masks:
        cache_out_path = d_data.cache_dir / (mask_data.target_path.stem + "_noise_mask.png")
        combined_noise_mask.save(cache_out_path)

    # Settle on the final output path for the cleaned image.
    if d_data.output_dir.is_absolute():
        final_out_path = d_data.output_dir / mask_data.target_path.name
    else:
        # Take the original image path, and place the image in a subdirectory.
        # This is for when multiple directories were passed in.
        final_out_path = (
            mask_data.target_path.parent / d_data.output_dir / mask_data.target_path.name
        )

    final_out_path.parent.mkdir(parents=True, exist_ok=True)
    final_cleaned_out_path = final_out_path.with_name(final_out_path.stem + "_clean.png")
    final_mask_out_path = final_out_path.with_name(final_out_path.stem + "_mask.png")
    final_mask_denoised_out_path = final_out_path.with_name(
        final_out_path.stem + "_denoised_mask.png"
    )

    # Check what the preferred output format is.
    if c_conf.preferred_file_type is None:
        # Use the original file type.
        final_cleaned_out_path = final_cleaned_out_path.with_suffix(mask_data.original_path.suffix)
    else:
        final_cleaned_out_path = final_cleaned_out_path.with_suffix(c_conf.preferred_file_type)

    if c_conf.preferred_mask_file_type is None:
        # Use png by default.
        final_mask_out_path = final_mask_out_path.with_suffix(".png")
    else:
        final_mask_out_path = final_mask_out_path.with_suffix(c_conf.preferred_mask_file_type)

    logger.debug(f"Final output path: {final_cleaned_out_path}")

    # The arg parser should ensure that both can't be true at once, not like that'd be an issue, just plain silly.
    if not d_data.save_only_mask:
        # Save the final image.
        logger.debug(f"Saving final image to {final_cleaned_out_path}")
        cleaned_image.save(final_cleaned_out_path)

    if not d_data.save_only_cleaned:
        # Save the final image.
        if d_data.separate_noise_masks:
            logger.debug(f"Saving final mask to {final_mask_out_path}")
            mask_image.save(final_mask_out_path)

            logger.debug(f"Saving final denoised mask to {final_mask_denoised_out_path}")
            combined_noise_mask.save(final_mask_denoised_out_path)
        else:
            # Combine both the mask and the denoised mask into one image.
            combined_noise_mask.paste(mask_image, (0, 0), mask_image)
            logger.debug(f"Saving final mask to {final_mask_out_path}")
            combined_noise_mask.save(final_mask_out_path)

    if d_data.extract_text:
        # Extract the text layer from the image.
        logger.debug(f"Extracting text from {mask_data.original_path}")
        base_image = Image.open(mask_data.original_path)
        text_img = ops.extract_text(base_image, mask_image)
        text_out_path = final_out_path.with_name(final_out_path.stem + "_text.png")
        if c_conf.preferred_mask_file_type is None:
            # Use png by default.
            text_out_path = text_out_path.with_suffix(".png")
        else:
            text_out_path = text_out_path.with_suffix(c_conf.preferred_mask_file_type)
        text_img.save(text_out_path)

    # Package the analytics. We're only interested in the std deviations.
    return st.DenoiseAnalytic(tuple(deviation for _, deviation in mask_data.boxes_with_deviation))
