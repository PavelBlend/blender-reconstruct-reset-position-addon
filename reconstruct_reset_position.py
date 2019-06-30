bl_info = {
    'name': 'Reconstruct Reset Position',
    'version': (0, 0, 0),
    'blender': (2, 79, 0),
    'category': 'Animation',
    'location': '3D View > Tool Shelf > Pose Tools',
}


import bpy
from mathutils import Matrix


def get_pose_matrix_in_other_space(mat, pose_bone):
    rest = pose_bone.bone.matrix_local.copy()
    rest_inv = rest.inverted()
    if pose_bone.parent:
        par_mat = pose_bone.parent.matrix.copy()
        par_inv = par_mat.inverted()
        par_rest = pose_bone.parent.bone.matrix_local.copy()
    else:
        par_mat = Matrix()
        par_inv = Matrix()
        par_rest = Matrix()
    smat = rest_inv * (par_rest * (par_inv * mat))
    return smat


def set_pose_rotation(pose_bone, mat):
    q = mat.to_quaternion()

    if pose_bone.rotation_mode == 'QUATERNION':
        pose_bone.rotation_quaternion = q
    elif pose_bone.rotation_mode == 'AXIS_ANGLE':
        pose_bone.rotation_axis_angle[0] = q.angle
        pose_bone.rotation_axis_angle[1] = q.axis[0]
        pose_bone.rotation_axis_angle[2] = q.axis[1]
        pose_bone.rotation_axis_angle[3] = q.axis[2]
    else:
        pose_bone.rotation_euler = q.to_euler(pose_bone.rotation_mode)


def match_pose_rotation(pose_bone, target_bone):
    mat = get_pose_matrix_in_other_space(target_bone.matrix, pose_bone)
    set_pose_rotation(pose_bone, mat)
    bpy.ops.object.mode_set(mode='POSE')



def set_pose_translation(pose_bone, mat):
    if pose_bone.bone.use_local_location == True:
        pose_bone.location = mat.to_translation()
    else:
        loc = mat.to_translation()

        rest = pose_bone.bone.matrix_local.copy()
        if pose_bone.bone.parent:
            par_rest = pose_bone.bone.parent.matrix_local.copy()
        else:
            par_rest = Matrix()

        q = (par_rest.inverted() * rest).to_quaternion()
        pose_bone.location = q * loc


def match_pose_translation(pose_bone, target_bone):
    mat = get_pose_matrix_in_other_space(target_bone.matrix, pose_bone)
    set_pose_translation(pose_bone, mat)
    bpy.ops.object.mode_set(mode='POSE')


def update_action(action):
    TOL = 0.005
    scene = bpy.context.scene
    obj = scene.objects.active
    obj.animation_data.action = action
    new_bones = [bone for bone in obj.pose.bones if bone.get('original_name') is not None]
    frame = action.frame_range[0]
    while frame <= action.frame_range[1]:
        scene.frame_set(frame)
        bpy.ops.object.mode_set(mode='POSE')
        for bone in new_bones:
            original_bone = obj.pose.bones.get(bone["original_name"])
            helper_bone = bone
            match_pose_translation(helper_bone, original_bone)
            helper_bone.keyframe_insert('location', group=helper_bone.name)
            match_pose_rotation(helper_bone, original_bone)
            if helper_bone.rotation_mode == 'QUATERNION':
                helper_bone.keyframe_insert('rotation_quaternion', group=helper_bone.name)
            elif helper_bone.rotation_mode == 'AXIS_ANGLE':
                helper_bone.keyframe_insert('rotation_axis_angle', group=helper_bone.name)
            else:
                helper_bone.keyframe_insert('rotation_euler', group=helper_bone.name)
        frame += 1
    bpy.ops.object.mode_set(mode='POSE')


def create_helper_bones():
    scene = bpy.context.scene
    original = bpy.context.active_object
    action = original.animation_data.action
    original.animation_data.action = None
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.duplicate()
    ob = scene.objects.active
    for bone in ob.pose.bones:
        bone['original_name'] = bone.name
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.armature_apply()
    bpy.ops.object.mode_set(mode='OBJECT')
    ob.select = True
    scene.objects.active = original
    scene.objects.active.select = True
    bpy.ops.object.join()
    original.animation_data.action = action


def remove_old_bones(bind_act):
    scene = bpy.context.scene
    obj = bpy.context.active_object
    bpy.ops.object.mode_set(mode='EDIT')
    for bone in obj.data.edit_bones:
        bose_bone = obj.pose.bones[bone.name]
        if bose_bone.get('original_name'):
            original_bone = obj.data.edit_bones[bose_bone['original_name']]
            obj.data.edit_bones.remove(original_bone)
            bone.name = bose_bone['original_name']
            del bose_bone['original_name']
    for action in bpy.data.actions:
        for fcurve in action.fcurves:
            if not '.001' in fcurve.data_path:
                action.fcurves.remove(fcurve)
            else:
                fcurve.group = action.groups[fcurve.group.name.split('.')[0]]
                bone_name = fcurve.data_path.split('"')[1].split('.')[0]
                data_path_parts = fcurve.data_path.split('"')
                fcurve.data_path = data_path_parts[0] + '"' + bone_name + '"' + data_path_parts[2]
    obj.animation_data.action = bind_act
    bpy.ops.object.mode_set(mode='POSE')


def reconstruct_bind_pose(obj, bind_act):
    obj.animation_data.action = bind_act
    meshes = [me for me in obj.children]
    bpy.ops.object.mode_set(mode='OBJECT')
    for me in meshes:
        bpy.ops.object.select_all(action='DESELECT')
        for mod in me.modifiers:
            if mod.type == 'ARMATURE':
                if mod.object == obj:
                    me.select = True
                    bpy.context.scene.objects.active = me
                    bpy.ops.object.modifier_apply(apply_as='DATA', modifier=mod.name)
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.scene.objects.active = obj
    obj.select = True
    bpy.ops.object.mode_set(mode='POSE')
    create_helper_bones()
    for action in bpy.data.actions:
        update_action(action)
    remove_old_bones(bind_act)
    for me in meshes:
        mod = me.modifiers.new('Armature', 'ARMATURE')
        mod.object = obj
    bpy.context.scene.frame_set(0)


class ReconstructBesetPosition(bpy.types.Operator):
    bl_idname = 'xray_import.level'
    bl_label = 'Reconstruct Reset Position'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(sel, context):
        obj = context.object
        act = obj.animation_data.action
        reconstruct_bind_pose(obj, act)
        return {'FINISHED'}


def draw_function(self, context):
    lay = self.layout
    lay.operator('xray_import.level')


def register():
    bpy.utils.register_class(ReconstructBesetPosition)
    bpy.types.VIEW3D_PT_tools_posemode.append(draw_function)


def unregister():
    bpy.types.VIEW3D_PT_tools_posemode.remove(draw_function)
    bpy.utils.unregister_class(ReconstructBesetPosition)
    
